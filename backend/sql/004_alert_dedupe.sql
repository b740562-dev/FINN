-- Alerts must be idempotent across scheduler runs: one alert per
-- (user, trigger). The trigger identity lives in dedupe_key, e.g.
-- 'move:DIXON:2026-11-09' or 'filing:123'.
alter table public.alerts add column if not exists event_date date;
alter table public.alerts add column if not exists dedupe_key text;
alter table public.alerts drop constraint if exists alerts_user_id_kind_symbol_filing_id_created_at_key;
create unique index if not exists alerts_user_dedupe on public.alerts (user_id, dedupe_key);
create index if not exists alerts_user_event on public.alerts (user_id, event_date desc);
