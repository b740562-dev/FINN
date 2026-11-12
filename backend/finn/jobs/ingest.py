"""Ingestion job: companies, EOD prices, screener fundamentals, and the
screener announcement feed (accumulated into `filings`).

Usage:
  python -m finn.jobs.ingest                 # demo universe
  python -m finn.jobs.ingest TCS HAL         # any NSE symbols
Safe to re-run: every write is an upsert.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict

from finn.db import cursor
from finn.sources.prices import fetch_eod
from finn.sources.screener import fetch_company
from finn.universe import PORTFOLIO, all_symbols

SECTOR = {h.symbol: h.sector for h in PORTFOLIO}


def load_demo_portfolio() -> None:
    with cursor() as c:
        c.execute(
            "insert into public.demo_portfolio (symbol, weight) "
            "select * from unnest(%s::text[], %s::numeric[]) "
            "on conflict (symbol) do update set weight = excluded.weight",
            ([h.symbol for h in PORTFOLIO], [h.weight for h in PORTFOLIO]),
        )
        c.execute("delete from public.demo_portfolio where not (symbol = any(%s::text[]))",
                  ([h.symbol for h in PORTFOLIO],))


def load_company(symbol: str) -> dict:
    """Company row + fundamentals + new filings, from one screener page."""
    page = fetch_company(symbol)
    with cursor() as c:
        c.execute(
            """insert into public.companies (symbol, name, bse_code, screener_id, sector, basis,
                                             market_cap_cr, updated_at)
               values (%s, %s, %s, %s, %s, %s, %s, now())
               on conflict (symbol) do update set name = excluded.name, bse_code = excluded.bse_code,
                 screener_id = excluded.screener_id, sector = coalesce(excluded.sector, companies.sector),
                 basis = excluded.basis, market_cap_cr = coalesce(excluded.market_cap_cr, companies.market_cap_cr),
                 updated_at = now()""",
            (symbol, page.name, page.bse_code, page.screener_id, SECTOR.get(symbol), page.basis,
             page.market_cap_cr),
        )
        c.execute(
            """insert into public.fundamentals (symbol, basis, tables, fetched_at)
               values (%s, %s, %s::jsonb, now())
               on conflict (symbol) do update set basis = excluded.basis, tables = excluded.tables,
                 fetched_at = now()""",
            (symbol, page.basis, json.dumps({k: asdict(v) for k, v in page.tables.items()})),
        )
        new = 0
        for a in page.announcements:
            if not a.date:
                continue
            key = hashlib.sha1(f"{symbol}|{a.date}|{a.title}".encode()).hexdigest()
            c.execute(
                """insert into public.filings (symbol, filed_at, subject, note, url, dedupe_key)
                   values (%s, %s::timestamptz, %s, %s, %s, %s)
                   on conflict (dedupe_key) do nothing returning id""",
                (symbol, a.date, a.title, a.note or None, a.url, key),
            )
            new += len(c.fetchall())
    try:                                   # newly published reports -> candidates for auto pickup
        from finn.pull.autodocs import record
        new_reports = record(symbol, page)
    except Exception:
        new_reports = 0
    return {"symbol": symbol, "new_filings": new, "new_reports": new_reports,
            "quarters": len(page.tables.get("quarters").columns)
            if "quarters" in page.tables else 0}


def load_prices(symbols: list[str], period: str = "6mo") -> int:
    data = fetch_eod(symbols, period=period)
    rows = 0
    with cursor() as c:
        for sym, df in data.items():
            c.execute(
                """insert into public.prices_eod (symbol, date, open, high, low, close, volume)
                   select * from unnest(%s::text[], %s::date[], %s::numeric[], %s::numeric[],
                                        %s::numeric[], %s::numeric[], %s::bigint[])
                   on conflict (symbol, date) do update set open = excluded.open, high = excluded.high,
                     low = excluded.low, close = excluded.close, volume = excluded.volume""",
                (
                    [sym] * len(df),
                    [d.strftime("%Y-%m-%d") for d in df.index],
                    [round(float(x), 4) for x in df["Open"]],
                    [round(float(x), 4) for x in df["High"]],
                    [round(float(x), 4) for x in df["Low"]],
                    [round(float(x), 4) for x in df["Close"]],
                    [int(x) for x in df["Volume"].fillna(0)],
                ),
            )
            rows += len(df)
    return rows


def main(symbols: list[str]) -> None:
    t0 = time.time()
    if symbols == all_symbols():
        load_demo_portfolio()
        print("demo_portfolio: loaded", len(PORTFOLIO))
    for i, sym in enumerate(symbols):
        try:
            r = load_company(sym)
            print(f"company {sym:12} quarters={r['quarters']:<3} new_filings={r['new_filings']} new_reports={r.get('new_reports', 0)}")
        except Exception as e:
            print(f"company {sym:12} FAILED: {type(e).__name__}: {str(e)[:150]}")
        if i < len(symbols) - 1:
            time.sleep(1.5)  # polite to screener
    n = load_prices(symbols)
    print(f"prices: {n} rows upserted")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:] or all_symbols())
