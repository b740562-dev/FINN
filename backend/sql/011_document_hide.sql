-- "Remove" in Your documents takes a report off the uploader's own list only.
-- The report stays in the shared library, so research and Surya keep using it
-- for everyone. (Admins can still delete a bad upload outright.)
alter table public.documents add column if not exists hidden_from_uploader_at timestamptz;
