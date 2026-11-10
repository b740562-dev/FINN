"""Data availability check for the demo universe (or any symbols passed in).

Usage:  python -m scripts.data_check [SYMBOL ...]
Writes backend/data/data_check.json and prints a summary table.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.sources.prices import fetch_eod, compute_signal  # noqa: E402
from finn.sources.screener import fetch_company  # noqa: E402
from finn.universe import all_symbols  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "data_check.json"


def main(symbols: list[str]) -> None:
    eod = fetch_eod(symbols)
    cutoff = (date.today() - timedelta(days=400)).isoformat()
    results = []
    for sym in symbols:
        row: dict = {"symbol": sym}
        sig = compute_signal(sym, eod[sym]) if sym in eod else None
        row["price_ok"] = sig is not None
        row["last_close_date"] = sig.date if sig else None
        row["vol_ratio"] = sig.volume_ratio if sig else None
        try:
            p = fetch_company(sym)
            q = p.tables.get("quarters")
            recent_calls = [c for c in p.concalls if c.date and c.date >= cutoff]
            row.update(
                screener_ok=True, name=p.name, basis=p.basis, bse_code=p.bse_code,
                quarters=len(q.columns) if q else 0,
                latest_quarter=q.columns[-1] if q else None,
                pl_years=len(p.tables["profit-loss"].columns) if "profit-loss" in p.tables else 0,
                annual_reports=len(p.annual_reports),
                latest_ar=p.annual_reports[0].year if p.annual_reports else None,
                transcripts_13m=sum(1 for c in recent_calls if c.transcript_url),
                announcements=len(p.announcements),
                latest_announcement=(p.announcements[0].date or "")[:10] if p.announcements else None,
                quarter_rows=list(q.rows.keys()) if q else [],
            )
        except Exception as e:  # keep going; report the failure
            row.update(screener_ok=False, error=str(e)[:200])
        results.append(row)
        time.sleep(1.5)  # be polite to screener

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    hdr = f"{'SYMBOL':12} {'PX':3} {'LAST':10} {'BASIS':12} {'BSE':7} {'QTRS':4} {'LATESTQ':9} {'PLY':3} {'AR':3} {'TRN':3} {'ANN':3} {'LAST ANN':10}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        if not r.get("screener_ok"):
            print(f"{r['symbol']:12} {'Y' if r['price_ok'] else 'N':3} {r['last_close_date'] or '-':10} SCREENER FAIL: {r.get('error')}")
            continue
        print(f"{r['symbol']:12} {'Y' if r['price_ok'] else 'N':3} {r['last_close_date'] or '-':10} "
              f"{r['basis']:12} {r['bse_code'] or '-':7} {r['quarters']:<4} {r['latest_quarter'] or '-':9} "
              f"{r['pl_years']:<3} {r['annual_reports']:<3} {r['transcripts_13m']:<3} {r['announcements']:<3} "
              f"{r['latest_announcement'] or '-':10}")


if __name__ == "__main__":
    main(sys.argv[1:] or all_symbols())
