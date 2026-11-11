"""Triggered alerts: the app watches for what the user defined as unusual.

- EOD price/volume: |day move| >= move_pct, or volume >= volume_multiple x
  the previous 20 sessions' average. Thresholds per user, with per-stock
  overrides ({"DIXON": {"move_pct": 3}}).
- Filings: a filing in a category the user cares about with materiality >=
  FILING_MIN.

Idempotent: every alert has a dedupe_key ('eod:DIXON:2026-11-09',
'filing:123'), so the scheduler can re-run freely. Evaluating a lookback
window (not just today) also backfills a new account's inbox.

Usage: python -m finn.push.alerts [lookback_days=30]
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time as dtime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

from finn.db import cursor

FILING_MIN = 60
AVG_WINDOW = 20

SIGNALS_SQL = f"""
with s as (
  select symbol, date, close, volume,
         lag(close) over (partition by symbol order by date) as prev_close,
         avg(volume) over (partition by symbol order by date
                           rows between {AVG_WINDOW} preceding and 1 preceding) as avg_vol,
         count(*)   over (partition by symbol order by date
                           rows between {AVG_WINDOW} preceding and 1 preceding) as n
  from public.prices_eod
  where symbol = any(%s::text[]) and date >= %s::date - interval '60 days'
)
select symbol, date, close, prev_close, volume, avg_vol
from s
where date >= %s::date and n = {AVG_WINDOW} and prev_close > 0 and avg_vol > 0
order by date
"""


def _signals(symbols: list[str], since: date) -> list[dict]:
    with cursor(commit=False) as c:
        c.execute(SIGNALS_SQL, (symbols, since, since))
        out = []
        for sym, d, close, prev, vol, avg in c.fetchall():
            close, prev, avg = float(close), float(prev), float(avg)
            out.append(dict(symbol=sym, date=d, close=close, prev_close=prev, volume=int(vol or 0),
                            avg_volume=round(avg), change_pct=round((close / prev - 1) * 100, 2),
                            volume_ratio=round((vol or 0) / avg, 2)))
        return out


def _users(user_id: str | None) -> list[dict]:
    with cursor(commit=False) as c:
        c.execute(
            """select r.user_id, r.volume_multiple, r.move_pct, r.categories, r.overrides,
                      coalesce(jsonb_object_agg(h.symbol, h.quantity) filter (where h.symbol is not null), '{}')
               from public.alert_rules r left join public.holdings h using (user_id)
               where (%s::uuid is null or r.user_id = %s::uuid)
               group by r.user_id, r.volume_multiple, r.move_pct, r.categories, r.overrides""",
            (user_id, user_id),
        )
        users = []
        for uid, vm, mp, cats, ov, qty in c.fetchall():
            qty = qty if isinstance(qty, dict) else json.loads(qty)
            users.append(dict(user_id=str(uid), volume_multiple=float(vm), move_pct=float(mp),
                              categories=list(cats or []), overrides=ov if isinstance(ov, dict) else json.loads(ov or "{}"),
                              quantity={k: float(v) if v is not None else None for k, v in qty.items()}))
        return users


def run_alerts(lookback_days: int = 30, user_id: str | None = None) -> dict:
    since = date.today() - timedelta(days=lookback_days)
    users = _users(user_id)
    symbols = sorted({s for u in users for s in u["quantity"]})
    if not symbols:
        return {"users": len(users), "created": 0}
    sigs = _signals(symbols, since)

    with cursor(commit=False) as c:
        c.execute("""select id, symbol, filed_at, category, materiality,
                            coalesce(enrichment->'results_card'->>'headline', one_liner, subject), url
                     from public.filings
                     where symbol = any(%s::text[]) and filed_at >= %s and materiality >= %s""",
                  (symbols, since, FILING_MIN))
        filings = c.fetchall()

    rows: list[tuple] = []   # (user_id, kind, symbol, filing_id, payload, event_date, dedupe_key, created_at)
    for u in users:
        held = u["quantity"]
        for s in sigs:
            if s["symbol"] not in held:
                continue
            ov = u["overrides"].get(s["symbol"], {})
            move_t = float(ov.get("move_pct", u["move_pct"]))
            vol_t = float(ov.get("volume_multiple", u["volume_multiple"]))
            triggers = []
            if abs(s["change_pct"]) >= move_t:
                triggers.append(f"move {s['change_pct']:+.1f}% (rule ±{move_t:g}%)")
            if s["volume_ratio"] >= vol_t:
                triggers.append(f"volume {s['volume_ratio']:.1f}x 20D avg (rule {vol_t:g}x)")
            if not triggers:
                continue
            qty = held.get(s["symbol"]) or 0
            payload = {**{k: v for k, v in s.items() if k != "date"}, "triggers": triggers,
                       "rule": {"move_pct": move_t, "volume_multiple": vol_t},
                       "impact_inr": round(qty * (s["close"] - s["prev_close"])) if qty else None}
            kind = "move" if abs(s["change_pct"]) >= move_t else "volume"
            closed_at = datetime.combine(s["date"], dtime(16, 0), tzinfo=IST)  # after market close
            rows.append((u["user_id"], kind, s["symbol"], None, json.dumps(payload), s["date"].isoformat(),
                         f"eod:{s['symbol']}:{s['date']}", closed_at.isoformat()))

        care = set(u["categories"])
        for fid, sym, ts, cat, mat, headline, url in filings:
            if sym not in held or cat not in care:
                continue
            payload = {"category": cat, "materiality": mat, "headline": headline, "url": url}
            rows.append((u["user_id"], "filing", sym, fid, json.dumps(payload), ts.date().isoformat(),
                         f"filing:{fid}", ts.isoformat()))

    created = {"eod": 0, "filing": 0}
    if rows:
        cols = list(zip(*rows))
        with cursor() as c:   # one round trip for the whole batch
            c.execute(
                """insert into public.alerts (user_id, kind, symbol, filing_id, payload, event_date, dedupe_key, created_at)
                   select * from unnest(%s::uuid[], %s::text[], %s::text[], %s::bigint[], %s::jsonb[],
                                        %s::date[], %s::text[], %s::timestamptz[])
                   on conflict (user_id, dedupe_key) do nothing returning kind""",
                [list(col) for col in cols],
            )
            for (kind,) in c.fetchall():
                created["filing" if kind == "filing" else "eod"] += 1
    return {"users": len(users), "signals_checked": len(sigs), "created": created}


if __name__ == "__main__":
    print(run_alerts(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
