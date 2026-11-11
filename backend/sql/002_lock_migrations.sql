-- schema_migrations lives in `public`, which Supabase's Data API exposes.
-- RLS with no policies = no access for anon/authenticated; the backend's
-- direct DB connection (table owner) is unaffected.
alter table public.schema_migrations enable row level security;
