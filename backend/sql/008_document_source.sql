-- Where an uploaded document came from (asked at upload), so research can show
-- provenance, and so a user can see and remove the documents they added.
alter table public.documents   add column if not exists source text;
alter table public.documents   add column if not exists source_url text;
alter table public.ingest_jobs add column if not exists source text;
alter table public.ingest_jobs add column if not exists source_url text;
create index if not exists documents_uploaded_by on public.documents (uploaded_by, ingested_at desc);
create index if not exists ingest_jobs_created_by on public.ingest_jobs (created_by, created_at desc);
