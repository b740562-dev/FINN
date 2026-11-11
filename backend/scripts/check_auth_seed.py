"""End-to-end check: guest sign-up -> trigger seeds portfolio -> RLS scopes reads.
Creates one anonymous test user and deletes it afterwards. Prints no secrets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from finn import config  # noqa: E402

URL = config.SUPABASE_URL
ANON = config.env("SUPABASE_ANON_KEY")
SERVICE = config.env("SUPABASE_SERVICE_ROLE_KEY")


def main() -> None:
    r = requests.post(f"{URL}/auth/v1/signup", headers={"apikey": ANON, "Content-Type": "application/json"},
                      json={}, timeout=20)
    if not r.ok:
        print("guest sign-up FAILED:", r.status_code, r.text[:300])
        return
    body = r.json()
    token, uid = body["access_token"], body["user"]["id"]
    print("guest sign-up OK, is_anonymous =", body["user"].get("is_anonymous"))
    h = {"apikey": ANON, "Authorization": f"Bearer {token}"}
    try:
        hold = requests.get(f"{URL}/rest/v1/holdings?select=symbol,weight,quantity&order=weight.desc",
                            headers=h, timeout=20).json()
        print(f"holdings seeded: {len(hold)} rows, weight sum = {sum(float(x['weight']) for x in hold):.1f}%")
        for x in hold[:4]:
            print(f"   {x['symbol']:12} {float(x['weight']):>5}%  qty={x['quantity']}")
        rules = requests.get(f"{URL}/rest/v1/alert_rules?select=volume_multiple,move_pct", headers=h, timeout=20).json()
        print("alert_rules:", rules)
        comps = requests.get(f"{URL}/rest/v1/companies?select=symbol", headers=h, timeout=20).json()
        print("shared read (companies):", len(comps), "rows")
        mig = requests.get(f"{URL}/rest/v1/schema_migrations?select=name", headers=h, timeout=20)
        print("schema_migrations via API:", mig.status_code, mig.text[:80])
        anon_hold = requests.get(f"{URL}/rest/v1/holdings?select=symbol", headers={"apikey": ANON}, timeout=20)
        print("holdings without login:", anon_hold.status_code, anon_hold.text[:80])
        write = requests.post(f"{URL}/rest/v1/companies", headers={**h, "Content-Type": "application/json"},
                              json={"symbol": "HACK", "name": "x"}, timeout=20)
        print("guest write to shared table:", write.status_code, write.text[:80])
    finally:
        d = requests.delete(f"{URL}/auth/v1/admin/users/{uid}",
                            headers={"apikey": SERVICE, "Authorization": f"Bearer {SERVICE}"}, timeout=20)
        print("test user deleted:", d.status_code)


if __name__ == "__main__":
    main()
