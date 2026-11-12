-- Surya chat history for logged-in (non-guest) accounts. Backend-only tables:
-- RLS on with no policies, every query is scoped to the caller's user id.
create table if not exists public.chat_threads (
  id          bigint generated always as identity primary key,
  user_id     uuid not null,
  title       text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists chat_threads_user on public.chat_threads (user_id, updated_at desc);

create table if not exists public.chat_messages (
  id          bigint generated always as identity primary key,
  thread_id   bigint not null references public.chat_threads(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  payload     jsonb,                 -- assistant: kind, citations (with source links), verified, companies
  created_at  timestamptz not null default now()
);
create index if not exists chat_messages_thread on public.chat_messages (thread_id, id);

alter table public.chat_threads  enable row level security;
alter table public.chat_messages enable row level security;
