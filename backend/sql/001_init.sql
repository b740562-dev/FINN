-- FINN schema v1
-- Shared market/AI data is global (processed once, read by everyone).
-- Portfolio, rules, alerts and push subscriptions are per user, behind RLS.

create extension if not exists vector with schema extensions;

-- ===================================================================
-- SHARED DATA (read-only to signed-in users; written by backend/cron)
-- ===================================================================

create table if not exists public.companies (
  symbol        text primary key,              -- NSE symbol
  name          text not null,
  bse_code      text,
  screener_id   text,
  sector        text,
  basis         text check (basis in ('consolidated','standalone')),
  updated_at    timestamptz not null default now()
);

create table if not exists public.prices_eod (
  symbol   text not null references public.companies(symbol) on delete cascade,
  date     date not null,
  open     numeric, high numeric, low numeric,
  close    numeric not null,
  volume   bigint,
  primary key (symbol, date)
);

-- Cached screener tables (quarters, P&L, BS, CF, ratios) per company.
create table if not exists public.fundamentals (
  symbol      text primary key references public.companies(symbol) on delete cascade,
  basis       text,
  tables      jsonb not null,
  fetched_at  timestamptz not null default now()
);

-- Exchange announcements, accumulated from screener's per-company feed.
create table if not exists public.filings (
  id            bigint generated always as identity primary key,
  symbol        text not null references public.companies(symbol) on delete cascade,
  filed_at      timestamptz not null,
  subject       text not null,                 -- BSE subject line
  note          text,                          -- short line shown under the subject, if any
  url           text,                          -- exchange PDF link (opens in user's browser)
  category      text,                          -- results, mgmt_change, M&A, ... (reference taxonomy)
  materiality   smallint,                      -- 0..100 base score before per-user weighting
  one_liner     text,                          -- FINN's line, only when it earns attention
  enrichment    jsonb,                         -- results table, person bio, etc.
  classified_by text,                          -- 'rules' | model id
  dedupe_key    text not null unique,
  first_seen_at timestamptz not null default now()
);
create index if not exists filings_symbol_time on public.filings (symbol, filed_at desc);
create index if not exists filings_time on public.filings (filed_at desc);

-- Uploaded primary documents (annual reports, concall transcripts).
create table if not exists public.documents (
  id           bigint generated always as identity primary key,
  symbol       text not null references public.companies(symbol) on delete cascade,
  kind         text not null check (kind in ('annual_report','transcript','results','presentation')),
  period       date,                           -- AR: fiscal year end; transcript: call month
  label        text,
  filename     text,
  sha256       text not null unique,
  pages        int,
  uploaded_by  uuid,
  ingested_at  timestamptz not null default now()
);

create table if not exists public.doc_chunks (
  id           bigint generated always as identity primary key,
  document_id  bigint not null references public.documents(id) on delete cascade,
  symbol       text not null,
  page         int not null,
  chunk_index  int not null,
  content      text not null,
  embedding    extensions.vector(768),
  tsv          tsvector generated always as (to_tsvector('english', content)) stored
);
create index if not exists doc_chunks_symbol on public.doc_chunks (symbol);
create index if not exists doc_chunks_tsv on public.doc_chunks using gin (tsv);
create index if not exists doc_chunks_embedding on public.doc_chunks
  using hnsw (embedding extensions.vector_cosine_ops);

-- Cached research output per company + section, keyed by the inputs it used.
create table if not exists public.dossier_sections (
  symbol       text not null references public.companies(symbol) on delete cascade,
  section      text not null,                  -- snapshot | promise_delivered | health | bull_bear
  inputs_hash  text not null,
  content      jsonb not null,
  model        text,
  created_at   timestamptz not null default now(),
  primary key (symbol, section, inputs_hash)
);

-- Every LLM call, for the cost & routing meter.
create table if not exists public.llm_calls (
  id          bigint generated always as identity primary key,
  task        text not null,
  model       text not null,
  tokens_in   int, tokens_out int,
  cost_usd    numeric(12,6),
  cache_hit   boolean not null default false,
  ref_type    text, ref_id text,
  created_at  timestamptz not null default now()
);

-- Seed portfolio every new account starts from.
create table if not exists public.demo_portfolio (
  symbol  text primary key,
  weight  numeric not null                      -- % of notional book
);

-- ===================================================================
-- PER-USER DATA (RLS: you see only your own rows)
-- ===================================================================

create table if not exists public.profiles (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  book_value   numeric not null default 5000000,   -- ₹50L notional
  created_at   timestamptz not null default now()
);

create table if not exists public.holdings (
  user_id   uuid not null references auth.users(id) on delete cascade,
  symbol    text not null references public.companies(symbol),
  quantity  numeric,
  weight    numeric,
  primary key (user_id, symbol)
);

create table if not exists public.alert_rules (
  user_id          uuid primary key references auth.users(id) on delete cascade,
  volume_multiple  numeric not null default 2.0,     -- volume > N x 20-day average
  move_pct         numeric not null default 5.0,     -- |day move| > X %
  categories       text[] not null default array['results','M&A','management_change','fund_raise','litigation','credit_rating','pledging'],
  overrides        jsonb not null default '{}'::jsonb -- per-symbol {volume_multiple, move_pct}
);

create table if not exists public.alerts (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  kind        text not null check (kind in ('volume','move','filing')),
  symbol      text not null,
  filing_id   bigint references public.filings(id) on delete set null,
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  read_at     timestamptz,
  pushed_at   timestamptz,
  unique (user_id, kind, symbol, filing_id, created_at)
);
create index if not exists alerts_user_time on public.alerts (user_id, created_at desc);

create table if not exists public.push_subscriptions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now()
);

-- ===================================================================
-- ROW LEVEL SECURITY
-- ===================================================================

alter table public.companies          enable row level security;
alter table public.prices_eod         enable row level security;
alter table public.fundamentals       enable row level security;
alter table public.filings            enable row level security;
alter table public.documents          enable row level security;
alter table public.doc_chunks         enable row level security;
alter table public.dossier_sections   enable row level security;
alter table public.llm_calls          enable row level security;
alter table public.demo_portfolio     enable row level security;
alter table public.profiles           enable row level security;
alter table public.holdings           enable row level security;
alter table public.alert_rules        enable row level security;
alter table public.alerts             enable row level security;
alter table public.push_subscriptions enable row level security;

-- Shared tables: any signed-in user (including guests) can read; only the
-- backend (service role / direct DB) writes.
do $$
declare t text;
begin
  foreach t in array array['companies','prices_eod','fundamentals','filings','documents',
                           'doc_chunks','dossier_sections','llm_calls','demo_portfolio']
  loop
    execute format('drop policy if exists "read shared" on public.%I', t);
    execute format('create policy "read shared" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

-- Per-user tables: full access to your own rows only.
do $$
declare t text;
begin
  foreach t in array array['profiles','holdings','alert_rules','alerts','push_subscriptions']
  loop
    execute format('drop policy if exists "own rows" on public.%I', t);
    execute format(
      'create policy "own rows" on public.%I for all to authenticated
         using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))', t);
  end loop;
end $$;

-- ===================================================================
-- NEW-USER SEEDING (runs for Google, email and guest sign-ups alike)
-- ===================================================================

create or replace function public.seed_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  insert into public.alert_rules (user_id) values (new.id) on conflict do nothing;

  -- Quantity = weight% x book / latest close (null until prices are loaded).
  insert into public.holdings (user_id, symbol, weight, quantity)
  select new.id, d.symbol, d.weight,
         floor((d.weight / 100.0) * 5000000 / nullif(p.close, 0))
  from public.demo_portfolio d
  left join lateral (
    select close from public.prices_eod pe
    where pe.symbol = d.symbol order by pe.date desc limit 1
  ) p on true
  on conflict do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.seed_new_user();
