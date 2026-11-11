-- Editable personal profile. All fields optional; visible only to the user
-- (profiles already has RLS "own rows").
alter table public.profiles add column if not exists full_name    text;
alter table public.profiles add column if not exists gender       text
  check (gender is null or gender in ('female', 'male', 'non_binary', 'prefer_not_to_say'));
alter table public.profiles add column if not exists work_company text;
alter table public.profiles add column if not exists work_role    text;
alter table public.profiles add column if not exists education    text;
alter table public.profiles add column if not exists city         text;
alter table public.profiles add column if not exists experience   text
  check (experience is null or experience in ('new', 'intermediate', 'experienced', 'professional'));
alter table public.profiles add column if not exists bio          text;
alter table public.profiles add column if not exists updated_at   timestamptz;
