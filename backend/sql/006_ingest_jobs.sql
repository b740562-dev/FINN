-- Background document ingestion: uploads return immediately with a job id;
-- the app polls the job while the PDF is read, indexed and analysed.
create table if not exists public.ingest_jobs (
  id          bigint generated always as identity primary key,
  symbol      text not null references public.companies(symbol) on delete cascade,
  filename    text,
  kind        text not null,
  period      date not null,
  status      text not null default 'queued'
              check (status in ('queued', 'reading', 'indexing', 'analysing', 'done', 'duplicate', 'failed')),
  result      jsonb,
  error       text,
  created_by  uuid,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists ingest_jobs_symbol on public.ingest_jobs (symbol, created_at desc);
alter table public.ingest_jobs enable row level security;   -- backend-only, no policies
