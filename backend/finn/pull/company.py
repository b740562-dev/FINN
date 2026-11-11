"""'Any NSE ticker' path: make sure a company exists in our DB, pulling it
from screener on first request (numbers + prices). Documents come later via
upload; numbers-based research works immediately."""
from __future__ import annotations

import re

from finn.db import cursor
from finn.http import get, make_session

_SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")


class CompanyNotFound(Exception):
    pass


def normalise(symbol: str) -> str:
    s = (symbol or "").strip().upper().removesuffix(".NS").removesuffix(".BO")
    if not _SYMBOL.match(s):
        raise CompanyNotFound(f"'{symbol}' is not a valid NSE symbol")
    return s


def company_meta(symbol: str) -> dict | None:
    with cursor(commit=False) as c:
        c.execute("""select co.symbol, co.name, co.sector, co.market_cap_cr, co.basis, co.bse_code, f.fetched_at
                     from public.companies co left join public.fundamentals f using (symbol)
                     where co.symbol = %s""", (symbol,))
        r = c.fetchone()
    if not r:
        return None
    return {"symbol": r[0], "name": r[1], "sector": r[2], "market_cap_cr": float(r[3]) if r[3] else None,
            "basis": r[4], "bse_code": r[5], "fundamentals_at": r[6].isoformat() if r[6] else None}


def ensure_company(symbol: str) -> dict:
    sym = normalise(symbol)
    meta = company_meta(sym)
    if meta and meta["fundamentals_at"]:
        with cursor(commit=False) as c:
            c.execute("select count(*) from public.prices_eod where symbol = %s", (sym,))
            has_prices = c.fetchone()[0] > 0
        if not has_prices:   # repair a half-loaded company (e.g. an earlier price fetch failed)
            from finn.jobs.ingest import load_prices
            load_prices([sym])
        return {**meta, "created": False}
    resp = get(make_session(), f"https://www.screener.in/company/{sym}/")
    if resp.status_code == 404 or "/company/" not in (resp.url or ""):
        raise CompanyNotFound(f"No listed company found for '{sym}'")
    from finn.jobs.ingest import load_company, load_prices
    load_company(sym)
    load_prices([sym])
    meta = company_meta(sym)
    if not meta:
        raise CompanyNotFound(f"Could not load '{sym}'")
    return {**meta, "created": True}
