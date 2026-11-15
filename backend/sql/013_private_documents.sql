-- A report added on the You page can't be vouched for (anyone can pick any PDF),
-- so it stays private: only its uploader's Surya and research Q&A read it.
-- Reports added from Research -> New reports (matched to an exchange listing)
-- are shared with everyone. null = shared.
alter table public.documents add column if not exists private_to uuid;
create index if not exists documents_private_to on public.documents (private_to) where private_to is not null;
