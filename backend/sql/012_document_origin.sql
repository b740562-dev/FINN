-- Where a user added a document from: 'you' (You -> Your documents), 'research'
-- (Research -> New reports) or 'surya' (the chat's pre-filled upload).
-- Your documents lists only what was added on the You page.
alter table public.documents   add column if not exists added_from text;
alter table public.ingest_jobs add column if not exists added_from text;
