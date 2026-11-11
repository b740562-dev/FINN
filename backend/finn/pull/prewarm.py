"""Pre-build research sections so nobody waits for a cold dossier.

Sections are cached by a hash of their inputs (reported tables + document
set + model), so this is cheap to re-run: anything unchanged returns from
cache instantly, and only companies whose numbers or documents changed are
rebuilt. The pipeline calls it after each refresh.

Usage: python -m finn.pull.prewarm [SYMBOL ...]
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from finn.db import cursor
from finn.pull import sections as S
from finn.universe import all_symbols

ORDER = ("snapshot", "health", "promise_delivered", "bull_bear")   # cheap first


def _one(symbol: str) -> dict:
    out = {"symbol": symbol}
    t0 = time.time()
    for sec in ORDER:
        t = time.time()
        try:
            r = S.get_section(symbol, sec)
            out[sec] = f"{r.get('status')}{'*' if r.get('cached') else ''} {time.time() - t:.1f}s"
        except Exception as e:
            out[sec] = f"error {type(e).__name__}"
    out["total_s"] = round(time.time() - t0, 1)
    return out


def prewarm(symbols: list[str] | None = None, workers: int = 3) -> list[dict]:
    if not symbols:
        symbols = list(all_symbols())
        with cursor(commit=False) as c:
            c.execute("select distinct symbol from public.holdings")
            symbols += [s for (s,) in c.fetchall() if s not in symbols]
    with cursor(commit=False) as c:
        c.execute("select symbol from public.fundamentals where symbol = any(%s::text[])", (symbols,))
        loaded = {s for (s,) in c.fetchall()}
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, s): s for s in symbols if s in loaded}
        for f in as_completed(futs):
            results.append(f.result())
    return sorted(results, key=lambda r: r["symbol"])


if __name__ == "__main__":
    t0 = time.time()
    rows = prewarm(sys.argv[1:] or None)
    for r in rows:
        print(f"{r['symbol']:11} " + "  ".join(f"{k}={r[k]}" for k in ORDER) + f"  ({r['total_s']}s)")
    print(f"{len(rows)} companies in {time.time() - t0:.0f}s   (* = served from cache)")
