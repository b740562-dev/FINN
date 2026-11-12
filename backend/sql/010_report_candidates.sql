-- Automatic report pickup. Every scheduler run records each company's newly
-- published concall transcripts, investor presentations and annual reports
-- (as listed on screener). FINN downloads the ones whose host serves plain
-- clients (company websites, some NSE archives), indexes them and rebuilds the
-- research; the rest (BSE refuses non-browser clients) wait as "needs_upload"
-- for a one-tap, pre-filled upload by any logged-in user.
create table if not exists public.report_candidates (
  id             bigint generated always as identity primary key,
  symbol         text not null references public.companies(symbol) on delete cascade,
  kind           text not null check (kind in ('annual_report', 'transcript', 'presentation')),
  period         date not null,            -- transcript/presentation: call month; annual report: FY end
  label          text not null,            -- "Q2 FY27 concall", "Annual Report FY26", ...
  url            text not null,            -- where screener points (often BSE)
  status         text not null default 'new'
                 check (status in ('new', 'ingested', 'needs_upload', 'failed', 'dismissed')),
  via            text,                     -- how it was obtained: direct | company_site | upload
  fetched_url    text,                     -- the URL actually downloaded (may differ: company site)
  document_id    bigint references public.documents(id) on delete set null,
  attempts       int not null default 0,
  last_error     text,
  discovered_at  timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (symbol, kind, period)
);
create index if not exists report_candidates_status on public.report_candidates (status, period desc);
alter table public.report_candidates enable row level security;   -- backend-only, no policies

alter table public.companies add column if not exists website text;
