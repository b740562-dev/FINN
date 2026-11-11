"""End-to-end API check against a running server (default http://localhost:8000).
Creates one guest account, exercises every endpoint, deletes the account."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from finn import config  # noqa: E402

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SB = config.SUPABASE_URL


def timed(method, path, **kw):
    t = time.time()
    r = requests.request(method, f"{API}{path}", timeout=60, **kw)
    return r, (time.time() - t) * 1000


def main() -> None:
    for _ in range(30):
        try:
            if requests.get(f"{API}/health", timeout=5).ok:
                break
        except requests.ConnectionError:
            time.sleep(1)
    r, ms = timed("GET", "/health")
    print(f"health {r.status_code} {r.json()} ({ms:.0f}ms)")
    r, _ = timed("GET", "/me")
    print("no token ->", r.status_code)

    s = requests.post(f"{SB}/auth/v1/signup", headers={"apikey": config.SUPABASE_ANON_KEY}, json={}, timeout=20).json()
    uid, h = s["user"]["id"], {"Authorization": f"Bearer {s['access_token']}"}
    try:
        r, ms = timed("POST", "/bootstrap", headers=h)
        print(f"bootstrap {r.status_code} {r.json()} ({ms:.0f}ms)")
        r, ms = timed("GET", "/me", headers=h)
        me = r.json()
        t = me["totals"]
        print(f"me {r.status_code} ({ms:.0f}ms): {len(me['holdings'])} holdings, value ₹{t['value']:,}, "
              f"day {t['day_pnl']:+,} ({t['day_pct']}%) as of {t['as_of']}, rules={me['rules']['move_pct']}%/"
              f"{me['rules']['volume_multiple']}x")
        top = me["holdings"][0]
        print(f"   top: {top['symbol']} qty {top['quantity']:.0f} @ {top['close']} = ₹{top['value']:,} ({top['weight']}%)")
        r, ms = timed("GET", "/me", headers=h)
        print(f"me again (token cached, pooled DB) {r.status_code} ({ms:.0f}ms)")

        for w in ("24h", "7d", "30d"):
            r, ms = timed("GET", f"/digest?window={w}", headers=h)
            d = r.json()
            first = d["matters"][0] if d["matters"] else None
            print(f"digest {w}: {d['counts']} ({ms:.0f}ms) top={first['symbol'] + ' ' + first['label'] if first else '-'}")
        r, _ = timed("GET", "/digest?window=24h&as_of=2026-11-02", headers=h)
        print("digest replay as_of 2026-11-02:", [f"{e['symbol']} {e['label']}" for e in r.json()["matters"]])

        r, ms = timed("GET", "/alerts", headers=h)
        a = r.json()
        print(f"alerts {r.status_code} ({ms:.0f}ms): {len(a['items'])} items, {a['unread']} unread")
        for it in a["items"][:4]:
            p = it["payload"]
            print(f"   {it['event_date']} {it['symbol']:10} {it['kind']:7} "
                  f"{'; '.join(p.get('triggers', [])) or p.get('headline', '')[:70]}"
                  f"{'  impact ₹' + format(p['impact_inr'], ',') if p.get('impact_inr') is not None else ''}")

        rules = requests.get(f"{API}/rules", headers=h, timeout=30).json()
        rules.pop("all_categories")
        rules["move_pct"] = 3.0
        rules["overrides"] = {"DIXON": {"move_pct": 2.0}}
        r, ms = timed("PUT", "/rules", headers=h, json=rules)
        print(f"rules -> move 3% + DIXON 2%: {r.status_code} {r.json()['alerts']} ({ms:.0f}ms)")
        r, _ = timed("GET", "/alerts", headers=h)
        print("   alerts now:", len(r.json()["items"]))
        r, _ = timed("POST", "/alerts/read", headers=h, json={})
        print("mark all read:", r.json())

        r, _ = timed("PUT", "/holdings", headers=h, json=[{"symbol": "INFY", "quantity": 100}, {"symbol": "NOPE", "quantity": 1}])
        print("holdings with unknown symbol ->", r.status_code, r.json()["detail"])
        r, _ = timed("PUT", "/holdings", headers=h, json=[{"symbol": "INFY", "quantity": 100}, {"symbol": "DIXON", "quantity": 10}])
        print("holdings INFY+DIXON ->", r.status_code, [(x["symbol"], x["weight"]) for x in r.json()["holdings"]])
        r, _ = timed("POST", "/holdings/reset", headers=h)
        print("reset ->", r.status_code, len(r.json()["holdings"]), "holdings")

        fid = next((e["filing_ids"][0] for e in requests.get(f"{API}/digest?window=30d", headers=h, timeout=30)
                    .json()["matters"] if e["category"] == "results"), None)
        r, _ = timed("GET", f"/filings/{fid}", headers=h)
        card = r.json()["enrichment"].get("results_card", {})
        print(f"filing {fid}: {r.json()['symbol']} -> {card.get('quarter_label')} {card.get('headline')}")
        r, _ = timed("GET", "/prices/RELIANCE?days=30", headers=h)
        print("prices RELIANCE 30d:", len(r.json()), "points")
        r, _ = timed("GET", "/companies?q=ta", headers=h)
        print("search 'ta':", [c["symbol"] for c in r.json()])
    finally:
        d = requests.delete(f"{SB}/auth/v1/admin/users/{uid}", timeout=20,
                            headers={"apikey": config.SUPABASE_SERVICE_ROLE_KEY,
                                     "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"})
        print("test user deleted:", d.status_code)


if __name__ == "__main__":
    main()
