"""Create / remove the local demo account used by local demo mode.

  python scripts/dev_demo_user.py create   # account + seeded portfolio + 30 days of alerts
  python scripts/dev_demo_user.py delete   # removes it (cascades to all its rows)

The account is written straight into Postgres (auth.users), so it works on a
network that blocks Supabase's HTTP APIs. The usual sign-up trigger seeds its
portfolio and alert rules exactly as for a real guest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.api.auth import DEV_USER_ID  # noqa: E402
from finn.db import cursor  # noqa: E402
from finn.push.alerts import run_alerts  # noqa: E402


def create() -> None:
    with cursor() as c:
        c.execute("""insert into auth.users (instance_id, id, aud, role, is_anonymous, created_at, updated_at)
                     values ('00000000-0000-0000-0000-000000000000', %s::uuid, 'authenticated', 'authenticated',
                             true, now(), now())
                     on conflict (id) do nothing""", (DEV_USER_ID,))
        c.execute("select count(*) from public.holdings where user_id = %s::uuid", (DEV_USER_ID,))
        print("demo account ready, holdings:", c.fetchone()[0])
    print("alerts backfilled:", run_alerts(lookback_days=30, user_id=DEV_USER_ID)["created"])


def delete() -> None:
    with cursor() as c:
        c.execute("delete from auth.users where id = %s::uuid", (DEV_USER_ID,))
        print("demo account removed:", c.rowcount)


if __name__ == "__main__":
    {"create": create, "delete": delete}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
