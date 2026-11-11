-- Market cap lets us size fund raises / deals against the company.
alter table public.companies add column if not exists market_cap_cr numeric;

-- Response cache for LLM calls: identical (model, prompt) never runs twice.
create table if not exists public.llm_cache (
  key         text primary key,          -- sha256 of model + config + prompt
  model       text not null,
  response    jsonb not null,
  created_at  timestamptz not null default now()
);
alter table public.llm_cache enable row level security;   -- backend-only, no policies

-- Feed ordering helpers.
create index if not exists filings_unclassified on public.filings (id) where category is null;
