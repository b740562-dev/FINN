"""Results first-cut: headline numbers for a quarter vs last quarter (QoQ) and
the same quarter last year (YoY).

Deterministic: no LLM touches these numbers. Source is screener's quarterly
table, which is compiled from the company's results filing.

Corporates: Revenue, EBITDA (screener "Operating Profit", before other
income), PBT, PAT + EBITDA and PAT margins.
Lenders (banks/NBFCs, detected by screener's "Financing Profit" layout):
EBITDA doesn't apply, so we show Revenue, Net interest income
(Revenue - Interest), PBT, PAT, and asset quality (GNPA/NNPA) when given.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from finn.db import cursor

MONTH = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}


def quarter_label(col: str) -> str:
    """'Sep 2026' -> 'Q2 FY27' (Indian fiscal year, April-March)."""
    mon, yr = col.split()
    m, y = MONTH[mon], int(yr)
    fy = y + 1 if m >= 4 else y
    q = {6: 1, 9: 2, 12: 3, 3: 4}[m]
    return f"Q{q} FY{str(fy)[-2:]}"


def quarter_end(col: str) -> date:
    mon, yr = col.split()
    m, y = MONTH[mon], int(yr)
    return date(y, m, 30 if m in (6, 9) else 31)


def latest_quarter_before(d: date) -> date:
    """Most recent quarter end strictly before date d (the quarter a results
    filing on d most likely reports)."""
    ends = [date(d.year - 1, 12, 31), date(d.year, 3, 31), date(d.year, 6, 30), date(d.year, 9, 30),
            date(d.year, 12, 31)]
    return max(e for e in ends if e < d)


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    if b < 0:  # growth off a loss base is not meaningful as a %
        return None
    return round((a / b - 1) * 100, 1)


def _metric(name: str, key: str, vals: list, i: int, kind: str = "amount") -> dict:
    cur = vals[i] if i < len(vals) else None
    prev = vals[i - 1] if i >= 1 else None
    yago = vals[i - 4] if i >= 4 else None
    m = {"name": name, "key": key, "kind": kind, "value": cur, "prev_q": prev, "year_ago": yago}
    if kind == "amount":
        m["qoq_pct"], m["yoy_pct"] = _pct(cur, prev), _pct(cur, yago)
    else:  # margin / ratio in %: change in basis points
        m["qoq_bp"] = None if cur is None or prev is None else round((cur - prev) * 100)
        m["yoy_bp"] = None if cur is None or yago is None else round((cur - yago) * 100)
    return m


def _margin(num: list, den: list) -> list:
    return [round(n / d * 100, 2) if n is not None and d not in (None, 0) else None for n, d in zip(num, den)]


def build_card(symbol: str, quarters: dict, basis: str, col: str | None = None) -> dict | None:
    cols: list[str] = quarters.get("columns", [])
    rows: dict = quarters.get("rows", {})
    if len(cols) < 2:
        return None
    i = cols.index(col) if col in cols else len(cols) - 1
    lender = "Financing Profit" in rows
    rev = rows.get("Sales") or rows.get("Revenue") or []
    pbt, pat = rows.get("Profit before tax", []), rows.get("Net Profit", [])
    metrics = [_metric("Revenue", "revenue", rev, i)]
    if lender:
        interest = rows.get("Interest", [])
        nii = [r - x if r is not None and x is not None else None for r, x in zip(rev, interest)]
        metrics.append(_metric("Net interest income", "nii", nii, i))
    else:
        ebitda = rows.get("Operating Profit", [])
        metrics.append(_metric("EBITDA", "ebitda", ebitda, i))
    metrics += [_metric("PBT", "pbt", pbt, i), _metric("PAT", "pat", pat, i)]

    margins = []
    if not lender:
        margins.append(_metric("EBITDA margin", "ebitda_margin", _margin(rows.get("Operating Profit", []), rev), i,
                               kind="ratio"))
    margins.append(_metric("PAT margin", "pat_margin", _margin(pat, rev), i, kind="ratio"))
    if lender:
        for lbl, key in (("Gross NPA", "gnpa"), ("Net NPA", "nnpa")):
            vals = rows.get(f"{lbl} %", [])
            if i < len(vals) and vals[i] is not None:
                margins.append(_metric(lbl, key, vals, i, kind="ratio"))

    return {
        "symbol": symbol,
        "quarter": cols[i],
        "quarter_label": quarter_label(cols[i]),
        "basis": basis,
        "unit": "₹ crore",
        "lender": lender,
        "metrics": metrics,
        "ratios": margins,
        "headline": headline(metrics, margins),
        "source": "Results filing, via screener.in quarterly table",
    }


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.0f}%" if abs(v) >= 10 else f"{v:+.1f}%"


def headline(metrics: list[dict], ratios: list[dict]) -> str:
    """Deterministic one-line read of the quarter (no LLM)."""
    by = {m["key"]: m for m in metrics}
    parts = [f"Revenue {_fmt_pct(by['revenue'].get('yoy_pct'))} YoY"]
    parts.append(f"PAT {_fmt_pct(by['pat'].get('yoy_pct'))} YoY")
    em = next((r for r in ratios if r["key"] == "ebitda_margin"), None)
    if em and em["value"] is not None and em.get("yoy_bp") is not None:
        parts.append(f"EBITDA margin {em['value']:.1f}% ({em['yoy_bp']:+d}bp YoY)")
    elif "nii" in by and by["nii"].get("yoy_pct") is not None:
        parts.append(f"NII {_fmt_pct(by['nii']['yoy_pct'])} YoY")
    # Flag profit growing much slower/faster than revenue: the thing to look at.
    r, p = by["revenue"].get("yoy_pct"), by["pat"].get("yoy_pct")
    if r is not None and p is not None and abs(p - r) >= 10:
        parts.append("profit lagging revenue" if p < r else "profit outpacing revenue")
    return "; ".join(parts)


import re  # noqa: E402

_CLAIM = [
    # "revenue rose 19%", "PAT up 28%", "sales grew by 12.5%"
    re.compile(r"\b(revenue|sales|income|pat|net profit|profit)\b[^.;%]{0,30}?"
               r"\b(?:up|rose|grew|growth|increased?|jumped|higher|declined?|fell|down)\b[^.;%]{0,12}?"
               r"(-?\d+(?:\.\d+)?)\s*%", re.I),
    # "19% revenue growth"
    re.compile(r"(-?\d+(?:\.\d+)?)\s*%\s*(revenue|sales|pat|net profit|profit)\s+(?:growth|rise|increase)", re.I),
]
_KEY = {"revenue": "revenue", "sales": "revenue", "income": "revenue",
        "pat": "pat", "net profit": "pat", "profit": "pat"}


def cross_check(card: dict, texts: list[str], tolerance_pp: float = 5.0) -> list[dict]:
    """Compare growth %s stated in the filing text with the card's YoY numbers."""
    by = {m["key"]: m for m in card["metrics"]}
    out = []
    for t in texts:
        for rx in _CLAIM:
            for m in rx.finditer(t or ""):
                g = m.groups()
                word, num = (g[0], g[1]) if not g[0][0].isdigit() and g[0][0] != "-" else (g[1], g[0])
                key = _KEY.get(word.lower())
                if not key or key not in by or by[key].get("yoy_pct") is None:
                    continue
                stated = float(num)
                if re.search(r"\b(declined?|fell|down)\b", m.group(0), re.I) and stated > 0:
                    stated = -stated
                ours = by[key]["yoy_pct"]
                out.append({"metric": by[key]["name"], "filing_text": m.group(0).strip(), "stated_pct": stated,
                            "card_yoy_pct": ours, "consistent": abs(stated - ours) <= tolerance_pp})
    # one entry per (metric, stated value)
    seen, uniq = set(), []
    for x in out:
        k = (x["metric"], x["stated_pct"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


_FLAGS = [
    (r"qualified (audit )?opinion|auditors? (issued|expressed) (a )?qualifi|modified opinion|"
     r"qualification", "Auditor qualified the accounts"),
    (r"emphasis of matter", "Auditor added an emphasis of matter"),
    (r"exceptional (loss|item|charge)", "Exceptional item in the quarter"),
    (r"going concern", "Going-concern language in the filing"),
    (r"restat", "Prior numbers restated"),
]


def red_flags(texts: list[str]) -> list[str]:
    """Deterministic red-flag phrases from the results filings' own text."""
    blob = " ".join(t or "" for t in texts).lower()
    return [label for pat, label in _FLAGS if re.search(pat, blob)]


def card_for_filing(symbol: str, filed_at: datetime, quarters: dict, basis: str) -> dict:
    """Card for the quarter a results filing reports. If screener hasn't added
    that quarter yet, return a 'pending' marker instead of stale numbers."""
    target = latest_quarter_before(filed_at.date())
    cols = quarters.get("columns", [])
    match = next((c for c in cols if quarter_end(c) == target), None)
    if not match:
        return {"status": "pending", "expected_quarter": target.isoformat(),
                "latest_available": cols[-1] if cols else None}
    card = build_card(symbol, quarters, basis, match)
    return {"status": "ready", **card} if card else {"status": "unavailable"}


def attach_results_cards() -> dict:
    """Store a results card on every results-category filing."""
    with cursor(commit=False) as c:
        c.execute("""select f.id, f.symbol, f.filed_at, fu.tables->'quarters', fu.basis,
                            -- text of every results filing for this company within 5 days
                            (select array_agg(concat_ws(' ', g.subject, g.note, g.one_liner))
                               from public.filings g
                              where g.symbol = f.symbol and g.category = 'results'
                                and abs(extract(epoch from g.filed_at - f.filed_at)) <= 5 * 86400)
                     from public.filings f join public.fundamentals fu using (symbol)
                     where f.category = 'results'""")
        rows = c.fetchall()
    stats = {"ready": 0, "pending": 0, "unavailable": 0, "mismatches": 0}
    with cursor() as c:
        for fid, sym, ts, q, basis, texts in rows:
            q = q if isinstance(q, dict) else json.loads(q or "{}")
            card = card_for_filing(sym, ts, q, basis)
            stats[card["status"]] += 1
            if card["status"] == "ready":
                card["cross_check"] = cross_check(card, texts or [])
                card["flags"] = red_flags(texts or [])
                stats["mismatches"] += sum(1 for x in card["cross_check"] if not x["consistent"])
            c.execute("update public.filings set enrichment = coalesce(enrichment, '{}'::jsonb) || "
                      "jsonb_build_object('results_card', %s::jsonb) where id = %s", (json.dumps(card), fid))
    return stats


if __name__ == "__main__":
    print(attach_results_cards())
