-- Research (pull side) helpers.
create index if not exists documents_symbol_kind on public.documents (symbol, kind, period desc);
create index if not exists doc_chunks_document on public.doc_chunks (document_id);
alter table public.documents add column if not exists chunks int;
alter table public.documents add column if not exists pages_kept int;
