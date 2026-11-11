"""Research dossier sections (the pull side).

Every section returns the same envelope:
  {"section", "status": "ready"|"needs_docs"|"error", "model", "generated_at",
   "content": {...}, "citations": [{"id","doc_id","doc_label","page","quote"}]}

Sources are primary only: screener's standardised tables (numbers) and the
company's own uploaded annual reports / concall transcripts. No web data and
no model background knowledge: prompts forbid it, numbers are computed in
code, and every quote a model returns is verified against the cited chunk.

Sections are cached in public.dossier_sections keyed by a hash of their
inputs (financial tables + document set + VERSION), so a dossier is computed
once and served instantly until the inputs change.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone

from finn import llm
from finn.db import cursor
from finn.pull.cite import chunk_block, citation, number_citation, quote_in, _squash
from finn.pull.retrieve import Chunk, documents, search
from finn.push.results import build_card, quarter_label

VERSION = "v1"
# Per-section versions: bumping one only invalidates that section's cache.
SECTION_VERSION = {"promise_delivered": "v7", "snapshot": "v3", "bull_bear": "v2"}   # v7: guidance pre-filter, computed periods, guards, YTD tracking
SECTIONS = ("snapshot", "health", "promise_delivered", "bull_bear")

PRIMARY_ONLY = ("Use ONLY the numbered excerpts and numbers given below. Do not use any outside or background "
                "knowledge about the company, its industry or news. If the material does not support a claim, "
                "leave it out.")


# ------------------------------------------------------------------ inputs
def _fund(symbol: str) -> dict:
    with cursor(commit=False) as c:
        c.execute("""select f.tables, f.basis, md5(f.tables::text), co.name, co.market_cap_cr
                     from public.fundamentals f join public.companies co using (symbol) where f.symbol = %s""",
                  (symbol,))
        r = c.fetchone()
    if not r:
        raise LookupError(f"No fundamentals for {symbol}")
    t = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    return {"tables": t, "basis": r[1], "md5": r[2], "name": r[3], "market_cap_cr": float(r[4]) if r[4] else None}


def _row(rows: dict, *names: str) -> list:
    for n in names:
        if n in rows:
            return rows[n]
    return []


def _is_lender(t: dict) -> bool:
    return "Financing Profit" in (t.get("profit-loss", {}).get("rows", {})) or \
        "Financing Profit" in (t.get("quarters", {}).get("rows", {}))


def _annual(t: dict, sec: str, years: list[str] | None = None) -> tuple[list[str], dict]:
    """Annual columns only (drops TTM and half-year interim columns)."""
    s = t.get(sec) or {}
    cols, rows = s.get("columns", []), s.get("rows", {})
    idx = [i for i, col in enumerate(cols) if col != "TTM" and (years is None or col in years)]
    return [cols[i] for i in idx], {k: [v[i] if i < len(v) else None for i in idx] for k, v in rows.items()}


def _cagr(series: list, n: int) -> float | None:
    vals = [v for v in series if v is not None]
    if len(vals) < n + 1 or vals[-n - 1] is None or vals[-n - 1] <= 0 or vals[-1] <= 0:
        return None
    return round(((vals[-1] / vals[-n - 1]) ** (1 / n) - 1) * 100, 1)


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


# ---------------------------------------------------------------- snapshot
def _financial(symbol: str, f: dict) -> dict:
    t = f["tables"]
    lender = _is_lender(t)
    pl = t.get("profit-loss", {})
    cols, rows = pl.get("columns", []), pl.get("rows", {})
    i = cols.index("TTM") if "TTM" in cols else len(cols) - 1
    rev = _row(rows, "Sales", "Revenue")
    pat = _row(rows, "Net Profit")
    op = [] if lender else _row(rows, "Operating Profit")
    g = lambda s: s[i] if i < len(s) else None  # noqa: E731
    ttm = {"revenue": g(rev), "ebitda": g(op) if op else None, "pat": g(pat)}
    ttm["ebitda_margin"] = _r(ttm["ebitda"] / ttm["revenue"] * 100) if ttm["ebitda"] and ttm["revenue"] else None
    ttm["pat_margin"] = _r(ttm["pat"] / ttm["revenue"] * 100) if ttm["pat"] is not None and ttm["revenue"] else None

    years, bs = _annual(t, "balance-sheet", [c for c in cols if c != "TTM"])
    eq = [(a or 0) + (b or 0) if a is not None or b is not None else None
          for a, b in zip(_row(bs, "Equity Capital"), _row(bs, "Reserves"))]
    debt = _row(bs, "Borrowings", "Borrowing")
    rcols, ratios = _annual(t, "ratios")
    roce = next((v for v in reversed(_row(ratios, "ROCE %")) if v is not None), None)
    roe = next((v for v in reversed(_row(ratios, "ROE %")) if v is not None), None)
    if roe is None and len(eq) >= 2 and eq[-1] and eq[-2]:
        ycols, pla = _annual(t, "profit-loss")
        last_pat = next((v for v in reversed(_row(pla, "Net Profit")) if v is not None), None)
        roe = _r(last_pat / ((eq[-1] + eq[-2]) / 2) * 100) if last_pat is not None else None
    de = None if lender or not eq or not eq[-1] or not debt or debt[-1] is None else round(debt[-1] / eq[-1], 2)
    q = t.get("quarters", {})
    return {"market_cap_cr": f["market_cap_cr"], "lender": lender, "ttm": ttm,
            "ratios": {"roce": roce, "roe": roe, "debt_to_equity": de, "as_of": years[-1] if years else None},
            "latest_quarter": build_card(symbol, q, f["basis"]) if q else None}


BUSINESS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "summary_support": {"type": "array", "items": {"type": "object", "properties": {
            "cite": {"type": "string"}, "quote": {"type": "string"}}, "required": ["cite", "quote"]}},
        "segments": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "share_pct": {"type": ["number", "null"]}, "note": {"type": "string"},
            "cite": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["name", "share_pct", "note", "cite", "quote"]}},
    },
    "required": ["summary", "summary_support", "segments"],
}


_BIZ = re.compile(r"\b(engaged in|(?:is|are|as) (?:a|an|one of|the|india'?s)\b[^.]{0,40}\b(?:leading|largest|"
                  r"company|manufacturer|player|brand|provider|enterprise)|leading \w+ (?:company|manufacturer|player)|"
                  r"we (?:offer|make|manufacture|provide|serve|operate)|our (?:products|business|portfolio|offerings?|"
                  r"customers|segments?|brands?)|business (?:overview|segments?|model)|segment[- ]wise|"
                  r"product (?:mix|portfolio|range)|revenue (?:from|mix|share)|manufactur\w+|markets? (?:we|in which)|"
                  r"customers? (?:include|across)|management discussion|industry structure|order book|home d[eé]cor|"
                  r"brands?|stores?|clients?)", re.I)
_NOTICE = re.compile(r"notice is hereby given|annual general meeting|ordinary resolution|special resolution|e-?voting|"
                     r"proxy|book closure|record date|remuneration of (?:the )?(?:statutory )?auditors?|"
                     r"registered office|scrutini[sz]er|video conferencing|dividend for the financial year", re.I)


def _business_chunks(symbol: str, limit: int = 10) -> list[Chunk]:
    """Passages that describe the business (latest annual report first), with the
    AGM notice / resolutions boilerplate excluded. Semantic search alone tends to
    land on the AGM notice at the front of the report."""
    with cursor(commit=False) as c:
        c.execute("""select dc.id, dc.document_id, d.label, d.kind, d.period::text, dc.page, dc.content
                     from public.doc_chunks dc join public.documents d on d.id = dc.document_id
                     where d.symbol = %s and d.kind = 'annual_report'
                       and d.id = (select max(id) from public.documents where symbol = %s and kind = 'annual_report')""",
                  (symbol, symbol))
        rows = c.fetchall()
    scored = []
    for cid, did, label, kind, period, page, text in rows:
        if _NOTICE.search(text):
            continue
        s = len(_BIZ.findall(text))
        if s >= 2:
            scored.append((s, cid, did, label, kind, period, page, text))
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:limit]
    chunks = [Chunk(chunk_id=cid, document_id=did, doc_label=label, kind=kind, period=period, page=page,
                    content=text, score=float(s)) for s, cid, did, label, kind, period, page, text in top]
    seen = {ch.chunk_id for ch in chunks}
    for ch in search(symbol, "business overview what the company does segments products customers", k=6):
        if ch.chunk_id not in seen and not _NOTICE.search(ch.content):   # semantic backstop
            seen.add(ch.chunk_id)
            chunks.append(ch)
    return chunks[:limit + 4]


def _business(symbol: str, name: str) -> tuple[dict | None, list[dict], dict]:
    chunks = _business_chunks(symbol)
    if not chunks:
        return None, [], {}
    block, refs = chunk_block(chunks)
    prompt = (f"Company: {name}\n{PRIMARY_ONLY}\n\nExcerpts:\n{block}\n\n"
              "Write what the company does (summary <= 60 words) and list its business segments. share_pct only "
              "if a revenue share is stated in the excerpts, else null. For every item give the excerpt id it "
              "comes from and a short VERBATIM quote (8-30 words) copied exactly from that excerpt.")
    out = llm.generate_json("research_business", prompt, BUSINESS_SCHEMA, model=llm.BULK, thinking="low",
                            ref_type="company", ref_id=symbol)
    cites: dict[str, dict] = {}
    dropped = 0

    def ok(cite: str, quote: str) -> str | None:
        nonlocal dropped
        cite = str(cite or "").strip("[] ")                      # model often writes "[c3]"
        ch = refs.get(cite)
        if not (ch and quote_in(quote, ch.content)):             # wrong id: accept a verbatim match anywhere
            hit = next(((k, c) for k, c in refs.items() if quote_in(quote, c.content)), None)
            cite, ch = hit if hit else (cite, None)
        if ch:
            cites.setdefault(cite, citation(cite, ch, quote))
            return cite
        dropped += 1
        return None

    support = [ok(s["cite"], s["quote"]) for s in out.get("summary_support", [])]
    support = [s for s in support if s]
    segs = []
    for s in out.get("segments", []):
        cid = ok(s["cite"], s["quote"])
        if cid:
            segs.append({"name": s["name"], "share_pct": s["share_pct"], "note": s["note"], "citation_id": cid})
    business = {"summary": out["summary"] if support else None, "summary_citations": support, "segments": segs}
    return business, list(cites.values()), {"dropped_quotes": dropped}


def snapshot(symbol: str) -> dict:
    f = _fund(symbol)
    fin = _financial(symbol, f)
    business, cits, ver, model = None, [], {}, None
    if documents(symbol):
        business, cits, ver = _business(symbol, f["name"])
        model = llm.BULK
    return _env("snapshot", "ready", model, {"financial": fin, "business": business, "verification": ver}, cits)


# ------------------------------------------------------------------ health
def health(symbol: str) -> dict:
    f = _fund(symbol)
    t = f["tables"]
    lender = _is_lender(t)
    years, pl = _annual(t, "profit-loss")
    years, pl = years[-10:], {k: v[-10:] for k, v in pl.items()}
    rev, pat = _row(pl, "Sales", "Revenue"), _row(pl, "Net Profit")
    opm = [] if lender else _row(pl, "OPM %")
    cagr = {"revenue_3y": _cagr(rev, 3), "revenue_5y": _cagr(rev, 5), "pat_3y": _cagr(pat, 3), "pat_5y": _cagr(pat, 5)}

    def trend_words() -> str:
        parts = []
        if cagr["revenue_5y"] is not None:
            parts.append(f"Revenue compounded {cagr['revenue_5y']:.0f}%/yr over 5 years")
        elif cagr["revenue_3y"] is not None:
            parts.append(f"Revenue compounded {cagr['revenue_3y']:.0f}%/yr over 3 years")
        p = cagr["pat_5y"] if cagr["pat_5y"] is not None else cagr["pat_3y"]
        if p is not None:
            parts.append(f"profit {p:.0f}%/yr")
        o = [v for v in opm if v is not None]
        if len(o) >= 4:
            prior = sum(o[-4:-1]) / 3
            d = o[-1] - prior
            parts.append(f"operating margin {'expanding' if d >= 2 else 'compressing' if d <= -2 else 'steady'} "
                         f"({o[-1]:.0f}% vs {prior:.0f}% avg of prior 3 yrs)")
        r3, p3 = cagr["revenue_3y"], cagr["pat_3y"]
        if r3 is not None and p3 is not None and abs(p3 - r3) >= 5:
            parts.append("profit growing faster than revenue" if p3 > r3 else "profit lagging revenue")
        return "; ".join(parts) or "Not enough history to judge the trajectory"

    byears, bs = _annual(t, "balance-sheet", years)
    eq = [(a or 0) + (b or 0) if a is not None or b is not None else None
          for a, b in zip(_row(bs, "Equity Capital"), _row(bs, "Reserves"))]
    debt = _row(bs, "Borrowings", "Borrowing")
    deposits = _row(bs, "Deposits")
    de = [round(d / e, 2) if d is not None and e else None for d, e in zip(debt, eq)]
    _, ratios = _annual(t, "ratios", byears)
    wcd = _row(ratios, "Working Capital Days")
    if lender:
        funded = (debt[-1] or 0) + ((deposits[-1] or 0) if deposits else 0) if debt else None
        bs_verdict = (f"Lender: borrowing is the business model, so D/E isn't a risk gauge. Equity of "
                      f"₹{eq[-1]:,.0f} cr funds ₹{funded:,.0f} cr of deposits + borrowings "
                      f"({funded / eq[-1]:.1f}x)." if eq and eq[-1] and funded else "Lender: D/E not meaningful.")
    else:
        d_last = next((v for v in reversed(de) if v is not None), None)
        lvl = None if d_last is None else ("net-cash-like / low" if d_last < 0.3 else "moderate" if d_last <= 1
                                           else "high")
        bs_verdict = f"Debt-to-equity {d_last:.2f} ({lvl})" if d_last is not None else "No borrowings data"
        d_prev = de[-4] if len(de) >= 4 else None
        if d_last is not None and d_prev is not None:
            bs_verdict += ", " + ("rising" if d_last - d_prev > 0.2 else "falling" if d_prev - d_last > 0.2
                                  else "stable") + " vs 3 years ago"
        w = [v for v in wcd if v is not None]
        if len(w) >= 4:
            bs_verdict += f"; working-capital days {w[-1]:.0f} ({'lengthening' if w[-1] - w[-4] > 15 else 'shortening' if w[-4] - w[-1] > 15 else 'stable'})"

    cyears, cf = _annual(t, "cash-flow", years)
    cfo = _row(cf, "Cash from Operating Activity")
    fcf = _row(cf, "Free Cash Flow")
    pat_by_year = dict(zip(years, pat))
    pat_c = [pat_by_year.get(y) for y in cyears]
    pairs = [(c, p) for c, p in zip(cfo[-5:], pat_c[-5:]) if c is not None and p is not None]
    conv = round(sum(c for c, _ in pairs) / sum(p for _, p in pairs) * 100) if pairs and sum(
        p for _, p in pairs) > 0 else None
    if lender:
        cash_verdict = "Lender: operating cash flow tracks loan and deposit growth, so profit-to-cash conversion isn't meaningful."
    elif conv is None:
        cash_verdict = "Not enough cash-flow history"
    else:
        tag = "strong" if conv >= 90 else "adequate" if conv >= 70 else "weak: profits are not turning into cash"
        cash_verdict = f"Operating cash flow was {conv}% of reported profit over the last {len(pairs)} years ({tag})"
        neg = sum(1 for v in fcf[-5:] if v is not None and v < 0)
        if neg:
            cash_verdict += f"; free cash flow negative in {neg} of the last {min(5, len(fcf))} years"

    content = {
        "lender": lender,
        "trajectory": {"years": years, "revenue": rev, "pat": pat, "opm": opm or None, "cagr": cagr,
                       "verdict": trend_words()},
        "balance_sheet": {"years": byears, "borrowings": debt, "deposits": deposits or None, "equity": eq,
                          "debt_to_equity": None if lender else de, "working_capital_days": wcd or None,
                          "verdict": bs_verdict},
        "cash": {"years": cyears, "cfo": cfo, "pat": pat_c, "fcf": fcf or None, "conversion_pct": conv,
                 "verdict": cash_verdict},
    }
    return _env("health", "ready", None, content, [])


# ----------------------------------------------------------- number facts
def number_facts(symbol: str) -> list[str]:
    """Deterministic one-line facts from snapshot + health, for bull/bear and Q&A."""
    snap = get_section(symbol, "snapshot")["content"]["financial"]
    h = get_section(symbol, "health")["content"]
    facts = []
    ttm = snap["ttm"]
    if ttm["revenue"]:
        facts.append(f"TTM revenue ₹{ttm['revenue']:,.0f} cr, PAT ₹{ttm['pat']:,.0f} cr"
                     + (f", EBITDA margin {ttm['ebitda_margin']}%" if ttm["ebitda_margin"] is not None else ""))
    if snap["market_cap_cr"] and ttm["pat"] and ttm["pat"] > 0:
        facts.append(f"Market cap ₹{snap['market_cap_cr']:,.0f} cr = {snap['market_cap_cr'] / ttm['pat']:.1f}x TTM PAT")
    r = snap["ratios"]
    if r["roce"] is not None:
        facts.append(f"ROCE {r['roce']}% ({r['as_of']})")
    if r["roe"] is not None:
        facts.append(f"ROE {r['roe']}%")
    lq = snap.get("latest_quarter")
    if lq:
        facts.append(f"{lq['quarter_label']}: {lq['headline']}")
    facts.append(h["trajectory"]["verdict"])
    facts.append(h["balance_sheet"]["verdict"])
    facts.append(h["cash"]["verdict"])
    return [f for f in facts if f]


# ------------------------------------------------------- promise vs delivered
PROMISE_SCHEMA = {
    "type": "object",
    "properties": {"promises": {"type": "array", "items": {"type": "object", "properties": {
        "metric": {"type": "string", "enum": ["revenue_growth", "volume_growth", "margin", "profit_growth", "capex",
                                              "other"]},
        "statement": {"type": "string"}, "target": {"type": "string"}, "target_period": {"type": "string"},
        "cite": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["metric", "statement", "target", "target_period", "cite", "quote"]}}},
    "required": ["promises"],
}
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"assessments": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"},
        "company_level": {"type": "boolean"},
        "tracking": {"type": "string", "enum": ["ahead", "on_track", "behind", "n/a"]},
        "verdict": {"type": "string", "enum": ["hit", "partial", "missed", "pending", "unverifiable"]},
        "actual": {"type": "string"}, "explanation": {"type": "string"}},
        "required": ["id", "company_level", "tracking", "verdict", "actual", "explanation"]}}},
    "required": ["assessments"],
}


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def _actuals_table(t: dict) -> str:
    """What was actually reported, as plain text for the model (and for the number guard)."""
    lender = _is_lender(t)
    q = t.get("quarters", {})
    cols, rows = q.get("columns", []), q.get("rows", {})
    rev, pat = _row(rows, "Sales", "Revenue"), _row(rows, "Net Profit")
    op = _row(rows, "Operating Profit")
    lines = ["QUARTERLY (₹ crore; Indian fiscal year Apr-Mar)",
             "quarter | revenue | revenue YoY % | " + ("PAT" if lender else "EBITDA margin % | PAT") + " | PAT YoY %"]
    for i in range(max(0, len(cols) - 8), len(cols)):
        ry = (rev[i] / rev[i - 4] - 1) * 100 if i >= 4 and rev[i] and rev[i - 4] else None
        py = (pat[i] / pat[i - 4] - 1) * 100 if i >= 4 and pat[i] and pat[i - 4] and pat[i - 4] > 0 else None
        m = op[i] / rev[i] * 100 if not lender and i < len(op) and op[i] is not None and rev[i] else None
        lines.append(f"{quarter_label(cols[i])} ({cols[i]}) | {_fmt(rev[i])} | {_fmt(ry)} | "
                     + ("" if lender else f"{_fmt(m)} | ") + f"{_fmt(pat[i])} | {_fmt(py)}")
    years, pl = _annual(t, "profit-loss")
    arev, apat, aopm = _row(pl, "Sales", "Revenue"), _row(pl, "Net Profit"), _row(pl, "OPM %")
    byears, bs = _annual(t, "balance-sheet", years)
    fa, cwip = _row(bs, "Fixed Assets"), _row(bs, "CWIP")
    dep = dict(zip(years, _row(pl, "Depreciation")))
    lines += ["", "ANNUAL (fiscal year ending)", "year | revenue | revenue growth % | OPM % | PAT | approx capex*"]
    for i in range(max(0, len(years) - 4), len(years)):
        g = (arev[i] / arev[i - 1] - 1) * 100 if i >= 1 and arev[i] and arev[i - 1] else None
        capex = None
        if years[i] in byears:
            j = byears.index(years[i])
            if j >= 1 and fa and fa[j] is not None and fa[j - 1] is not None:
                capex = (fa[j] - fa[j - 1]) + ((cwip[j] or 0) - (cwip[j - 1] or 0) if cwip else 0) + (dep.get(years[i]) or 0)
        fy = f"FY{str(int(years[i][-4:]))[-2:]}" if years[i].startswith("Mar") else years[i]
        lines.append(f"{fy} ({years[i]}) | {_fmt(arev[i])} | {_fmt(g)} | "
                     f"{_fmt(aopm[i] if i < len(aopm) else None)} | {_fmt(apat[i])} | {_fmt(capex)}")
    lines.append("*approx capex = change in net fixed assets + change in CWIP + depreciation")
    lines.append(f"Latest reported quarter: {quarter_label(cols[-1]) if cols else 'n/a'}. Today: {date.today()}.")
    return "\n".join(lines)


_NUMS = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _numbers_ok(text: str, allowed_text: str) -> bool:
    allowed = [float(x.replace(",", "")) for x in _NUMS.findall(allowed_text)]
    for x in _NUMS.findall(text or ""):
        v = float(x.replace(",", ""))
        if abs(v) < 5 and "." not in x:   # small integers (Q2, 3 years...) are not data claims
            continue
        if not any(abs(v - a) <= max(0.6, abs(a) * 0.01) for a in allowed):
            return False
    return True


_FWD = re.compile(r"\b(guid\w*|outlook|we expect|expect(?:ing|ed)? (?:to|that)|target\w*|aim\w*|going forward|"
                  r"next (?:year|quarter|few quarters|fiscal)|FY\s?'?2[6-9]|H[12]\b|second half|full year|"
                  r"will (?:be|grow|improve|deliver|reach|cross)|should (?:be|grow)|trajectory|run[- ]rate|"
                  r"double[- ]digit|mid[- ]teens|high[- ]single|range of|band of|order inflow|capex)", re.I)
_QUANT = re.compile(r"\d+(?:\.\d+)?\s?(?:%|percent|bps|basis points|crore|cr\b|billion|bn\b|million)|"
                    r"double[- ]digit|mid[- ]teens|high[- ]single|low[- ]teens", re.I)
_BOILER = re.compile(r"registered (?:&|and) corporate office|MANAGEMENT:|Ladies and gentlemen|"
                     r"forward[- ]looking statements|safe harbou?r|this transcript", re.I)


def _guidance_chunks(doc_id: int, limit: int = 30) -> list[Chunk]:
    """Deterministic pre-filter: the passages of a transcript most likely to
    hold guidance (forward-looking language + a number or range), minus the
    cover letter / disclaimer boilerplate. Cheap, and far more reliable than
    semantic search for this (which tends to return the cover page)."""
    with cursor(commit=False) as c:
        c.execute("""select dc.id, dc.document_id, d.label, d.kind, d.period::text, dc.page, dc.content
                     from public.doc_chunks dc join public.documents d on d.id = dc.document_id
                     where dc.document_id = %s order by dc.chunk_index""", (doc_id,))
        rows = c.fetchall()
    scored = []
    for cid, did, label, kind, period, page, text in rows:
        fwd, qnt = len(_FWD.findall(text)), len(_QUANT.findall(text))
        s = 2 * min(fwd, 4) + 2 * min(qnt, 3) + (3 if fwd and qnt else 0) - (8 if _BOILER.search(text) else 0)
        if s >= 4:
            scored.append((s, cid, did, label, kind, period, page, text))
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:limit]
    return [Chunk(chunk_id=cid, document_id=did, doc_label=label, kind=kind, period=period, page=page,
                  content=text, score=float(s))
            for s, cid, did, label, kind, period, page, text in sorted(top, key=lambda x: x[1])]


_VAGUE = re.compile(r"medium[- ]term|mid[- ]?term|long[- ]term|near[- ]term|future|years?\b|next few|upcoming|"
                    r"coming quarters|over time|with scale|eventually|gradual", re.I)


def _fyq(label: str) -> tuple[int, int] | None:
    """'Q2 FY27' / 'Q2 FY27 concall' -> (27, 2)."""
    m = re.search(r"Q([1-4])\s*FY\s*'?(\d{2,4})", label or "", re.I)
    return (int(m.group(2)[-2:]), int(m.group(1))) if m else None


def _period_status(period: str, said_in: str, latest: tuple[int, int] | None) -> str:
    """Has the target period been fully reported? 'complete' | 'future' | 'unknown'.
    Deterministic, so a model can't judge FY27 guidance against FY26 numbers."""
    if not latest or not period:
        return "unknown"
    p = period.strip()
    said = _fyq(said_in)
    ly, lq = latest

    def done(fy: int, q: int) -> str:
        return "complete" if (fy, q) <= (ly, lq) else "future"

    if m := re.search(r"\bQ([1-4])\s*FY\s*'?(\d{2,4})", p, re.I):
        return done(int(m.group(2)[-2:]), int(m.group(1)))
    if m := re.search(r"\bH([12])\s*FY\s*'?(\d{2,4})", p, re.I):
        return done(int(m.group(2)[-2:]), 2 if m.group(1) == "1" else 4)
    if m := re.search(r"\bH([12])\b|(first|second) half", p, re.I):
        if said:
            half = "1" if (m.group(1) == "1" or (m.group(2) or "").lower() == "first") else "2"
            return done(said[0], 2 if half == "1" else 4)
    if m := re.search(r"FY\s*'?(\d{2,4})", p, re.I):
        return done(int(m.group(1)[-2:]), 4)
    if re.search(r"next quarter", p, re.I) and said:
        fy, q = said
        return done(fy + (q == 4), 1 if q == 4 else q + 1)
    if re.search(r"next (fiscal )?year", p, re.I) and said:
        return done(said[0] + 1, 4)
    if re.search(r"full year|this year|the year|current year|for the year", p, re.I) and said:
        return done(said[0], 4)
    if _VAGUE.search(p):
        return "future"
    return "unknown"


def _target_key(period: str, said_in: str):
    """Resolve a target period to ('Q', fy, q) | ('H', fy, half) | ('FY', fy) | None."""
    p, said = (period or "").strip(), _fyq(said_in)
    if m := re.search(r"\bQ([1-4])\s*FY\s*'?(\d{2,4})", p, re.I):
        return ("Q", int(m.group(2)[-2:]), int(m.group(1)))
    if m := re.search(r"\bH([12])\s*FY\s*'?(\d{2,4})", p, re.I):
        return ("H", int(m.group(2)[-2:]), int(m.group(1)))
    if (m := re.search(r"\bH([12])\b|(first|second) half", p, re.I)) and said:
        return ("H", said[0], 1 if (m.group(1) == "1" or (m.group(2) or "").lower() == "first") else 2)
    if m := re.search(r"FY\s*'?(\d{2,4})", p, re.I):
        return ("FY", int(m.group(1)[-2:]))
    if re.search(r"next quarter", p, re.I) and said:
        fy, q = said
        return ("Q", fy + (q == 4), 1 if q == 4 else q + 1)
    if re.search(r"next (fiscal )?year", p, re.I) and said:
        return ("FY", said[0] + 1)
    if re.search(r"full year|this year|the year|current year|for the year", p, re.I) and said:
        return ("FY", said[0])
    return None


def _actual_matches_period(actual: str, period: str, said_in: str) -> bool:
    """If the 'actual' names periods, at least one must be the target period.
    Stops e.g. FY26 guidance being scored with FY25 numbers."""
    key = _target_key(period, said_in)
    if not key:
        return True
    qs = [(int(y[-2:]), int(q)) for q, y in re.findall(r"\bQ([1-4])\s*FY\s*'?(\d{2,4})", actual or "", re.I)]
    fys = [int(y[-2:]) for y in re.findall(r"(?<!Q[1-4] )\bFY\s*'?(\d{2,4})\b", actual or "", re.I)]
    if not qs and not fys:
        return True   # nothing to check against
    if key[0] == "Q":
        return (key[1], key[2]) in qs
    if key[0] == "H":
        rng = (1, 2) if key[2] == 1 else (3, 4)
        return any(fy == key[1] and q in rng for fy, q in qs) or key[1] in fys
    return key[1] in fys or any(fy == key[1] for fy, _ in qs)


def _extract_promises(symbol: str, company: str, d: dict) -> list[tuple[dict, Chunk | None, bool]]:
    """Guidance statements from one transcript: [(promise, cited chunk, quote verified?)]."""
    chunks = _guidance_chunks(d["id"])
    seen = {ch.chunk_id for ch in chunks}
    for q in ("guidance outlook we expect growth for the year", "margin band EBITDA margin expect range"):
        for ch in search(symbol, q, k=4, document_ids=[d["id"]]):   # semantic backstop
            if ch.chunk_id not in seen and not _BOILER.search(ch.content):
                seen.add(ch.chunk_id)
                chunks.append(ch)
    if not chunks:
        return []
    block, refs = chunk_block(chunks)
    prompt = (f"Company: {company}. Source: {d['label']} transcript.\n{PRIMARY_ONLY}\n\nExcerpts:\n{block}\n\n"
              "List the forward-looking statements MANAGEMENT made (not analysts' questions) that can later be "
              "checked against reported numbers: revenue/volume growth, margins, profit, capex, order inflow, or "
              "other targets. Include explicit numbers and ranges (e.g. '12-14% growth', '27% EBITDA margin') AND "
              "checkable directional guidance (e.g. 'double-digit growth', 'H2 better than H1', 'margins to "
              "improve from here'). Skip vague optimism with no checkable claim. Max 6. For each: the excerpt id "
              "and a VERBATIM quote (10-35 words) copied exactly from it; target as stated; target_period like "
              "'FY27', 'H2 FY27', 'Q3 FY27', 'next 2-3 years'.")
    out = llm.generate_json("promise_extract", prompt, PROMISE_SCHEMA, model=llm.BULK, thinking="low",
                            ref_type="document", ref_id=str(d["id"]))
    res = []
    for p in out.get("promises", []):
        ch = refs.get(str(p.get("cite", "")).strip("[] "))   # model often writes "[c8]"
        # The model sometimes cites the wrong excerpt id: accept the quote if it is verbatim in ANY excerpt.
        if ch is None or not quote_in(p["quote"], ch.content):
            ch = next((c for c in chunks if quote_in(p["quote"], c.content)), None)
        res.append((p, ch, ch is not None))
    return res


def promise_delivered(symbol: str) -> dict:
    f = _fund(symbol)
    transcripts = [d for d in documents(symbol) if d["kind"] == "transcript"][:4]
    if not transcripts:
        return _env("promise_delivered", "needs_docs", None,
                    {"reason": "Upload the last 4 concall transcripts to compare guidance with delivery.",
                     "score": None, "items": []}, [])
    promises, cites, dropped, seen_quotes = [], {}, 0, set()
    for d in transcripts:
        extracted = _extract_promises(symbol, f["name"], d)
        # Checkable promises first: an explicit number in the target, then a concrete period.
        extracted.sort(key=lambda x: (not re.search(r"\d", str(x[0].get("target", ""))),
                                      _target_key(str(x[0].get("target_period", "")), d["label"]) is None))
        kept_here = 0
        for p, ch, ok in extracted:
            if not ok:
                dropped += 1
                continue
            key = _squash(p["quote"])
            if key in seen_quotes or kept_here >= 5:   # no repeats; keep older calls represented
                continue
            seen_quotes.add(key)
            kept_here += 1
            cid = f"c{len(cites) + 1}"
            cites[cid] = citation(cid, ch, p["quote"])
            promises.append({**p, "said_in": d["label"], "citation_id": cid})
    promises = promises[:18]
    if not promises:
        return _env("promise_delivered", "ready", llm.BULK,
                    {"score": {k: 0 for k in ("hit", "partial", "missed", "pending", "unverifiable")},
                     "items": [], "note": "No explicit quantified guidance found in the uploaded transcripts.",
                     "verification": {"dropped_quotes": dropped}}, list(cites.values()))

    actuals = _actuals_table(f["tables"])
    cols = f["tables"].get("quarters", {}).get("columns", [])
    latest = _fyq(quarter_label(cols[-1])) if cols else None          # e.g. (27, 2) for Q2 FY27
    for p in promises:
        p["period_status"] = _period_status(p["target_period"], p["said_in"], latest)
    status_txt = {"future": "NOT YET FULLY REPORTED", "complete": "fully reported", "unknown": "unclear"}
    plist = "\n".join(f"p{i + 1}: [{p['said_in']}] {p['metric']}: {p['statement']} | target: {p['target']} | "
                      f"period: {p['target_period']} ({status_txt[p['period_status']]})" for i, p in enumerate(promises))
    latest_txt = f"Q{latest[1]} FY{latest[0]}" if latest else "n/a"
    prompt = (f"Company: {f['name']}.\n{PRIMARY_ONLY}\n\nMANAGEMENT PROMISES\n{plist}\n\nREPORTED NUMBERS\n{actuals}\n\n"
              f"Latest reported quarter: {latest_txt}. Each promise's period status was computed from that.\n"
              "For each promise decide: hit (delivered at/above target), partial (close or part-delivered), missed, "
              "pending (target period not fully reported yet), or unverifiable (no matching reported metric, e.g. "
              "segment, store, client or volume data not in the table). Only judge a period against numbers FOR "
              "THAT PERIOD, never an earlier year. For a period NOT YET FULLY REPORTED, the verdict is pending, and "
              "tracking says whether the reported quarters of that period so far are ahead of, on track for, or "
              "behind the target (n/a if no quarters of that period are reported or it isn't a table metric); "
              "'actual' may show the reported quarters so far (e.g. 'H1 FY27 margin 19.8%, tracking below'). "
              "'actual' must quote numbers ONLY from REPORTED NUMBERS (or be 'n/a'), and name the period each number "
              "is for (e.g. 'Q4 FY26', 'FY26'). company_level: true only if the promise is about a whole-company "
              "metric in the table (revenue, EBITDA/OPM margin, PAT, capex); false for a segment, product, "
              "geography, client, store count or order inflow. explanation <= 30 words.")
    out = llm.generate_json("promise_verdict", prompt, VERDICT_SCHEMA, model=llm.REASON, thinking="medium",
                            ref_type="company", ref_id=symbol)
    by_id = {a["id"]: a for a in out.get("assessments", [])}
    items, guarded, corrected = [], 0, 0
    for i, p in enumerate(promises):
        a = by_id.get(f"p{i + 1}") or {"verdict": "unverifiable", "actual": "n/a", "explanation": "Not assessed."}
        verdict, actual, expl = a["verdict"], a["actual"], a["explanation"]
        if not _numbers_ok(actual, actuals + " " + p["target"]):
            guarded += 1
            verdict, actual, expl = "unverifiable", "n/a", "Could not match the claimed actual to reported numbers."
        # Calendar logic is computed, not generated: a period that isn't over can't be hit or missed,
        # and a hit/miss needs an actual number behind it.
        if p["period_status"] == "future" and verdict in ("hit", "missed", "partial"):
            corrected += 1
            expl = f"{p['target_period']} isn't fully reported yet (latest: {latest_txt}). " + expl
            verdict = "pending"
        if verdict in ("hit", "missed", "partial") and actual.strip().lower() in ("n/a", "na", "", "none"):
            corrected += 1
            verdict, expl = "unverifiable", "No reported metric matches this target."
        if verdict in ("hit", "missed", "partial") and a.get("company_level") is False:
            corrected += 1
            verdict, expl = "unverifiable", "A segment/product-level target; only company-level numbers are reported."
        if verdict in ("hit", "missed", "partial") and not _actual_matches_period(actual, p["target_period"],
                                                                                 p["said_in"]):
            corrected += 1
            verdict, expl = "unverifiable", f"The reported numbers cited aren't for {p['target_period']}."
        # Year-to-date read for unfinished periods, only when backed by numbers for that same period.
        tracking = a.get("tracking", "n/a")
        if (verdict != "pending" or a.get("company_level") is False or actual.strip().lower() in ("n/a", "na", "")
                or not _actual_matches_period(actual, p["target_period"], p["said_in"])
                or _target_key(p["target_period"], p["said_in"]) is None):
            tracking = "n/a"
        items.append({"promise": p["statement"], "said_in": p["said_in"], "metric": p["metric"], "target": p["target"],
                      "target_period": p["target_period"], "actual": actual, "verdict": verdict, "explanation": expl,
                      "tracking": tracking, "citation_id": p["citation_id"]})
    score = {k: sum(1 for x in items if x["verdict"] == k) for k in ("hit", "partial", "missed", "pending",
                                                                       "unverifiable")}
    return _env("promise_delivered", "ready", llm.REASON,
                {"score": score, "items": items, "transcripts_used": [d["label"] for d in transcripts],
                 "verification": {"dropped_quotes": dropped, "actuals_guarded": guarded,
                                  "verdicts_corrected": corrected}}, list(cites.values()))


# ---------------------------------------------------------------- bull/bear
BB_POINT = {"type": "object", "properties": {
    "title": {"type": "string"},
    "stat": {"type": "string"},
    "point": {"type": "string"},
    "refs": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["id", "quote"]}}},
    "required": ["title", "stat", "point", "refs"]}
BB_SCHEMA = {"type": "object", "properties": {"bull": {"type": "array", "items": BB_POINT},
                                              "bear": {"type": "array", "items": BB_POINT}},
             "required": ["bull", "bear"]}


def bull_bear(symbol: str) -> dict:
    f = _fund(symbol)
    facts = number_facts(symbol)
    nrefs = {f"n{i + 1}": fact for i, fact in enumerate(facts)}
    chunks: list[Chunk] = []
    if documents(symbol):
        seen = set()
        for q in ("key risks challenges headwinds pressure decline concern",
                  "growth drivers opportunities demand order book expansion new products"):
            for ch in search(symbol, q, k=5):
                if ch.chunk_id not in seen:
                    seen.add(ch.chunk_id)
                    chunks.append(ch)
    block, crefs = chunk_block(chunks)
    numbers = "\n".join(f"[{k}] {v}" for k, v in nrefs.items())
    prompt = (f"Company: {f['name']}.\n{PRIMARY_ONLY}\n\nNUMBER FACTS\n{numbers}\n\n"
              + (f"DOCUMENT EXCERPTS\n{block}\n\n" if chunks else "")
              + "Write a tight bull case and bear case: exactly 3 points each, specific, no hype. For each point:\n"
                "- title: 2-5 words naming the idea (e.g. 'Capital efficient', 'Margin squeeze', 'Order book visibility')\n"
                "- stat: the ONE figure that proves it, as a short label + number copied from the cited facts or "
                "excerpts (e.g. 'ROCE 36%', 'CFO 59% of PAT', 'D/E 0.0x'); '' if no single figure fits\n"
                "- point: one sentence <= 20 words\n"
                "Every point must cite at least one id from NUMBER FACTS (n#) or DOCUMENT EXCERPTS (c#). For c# ids "
                "include a VERBATIM quote (8-30 words) copied exactly from that excerpt; for n# ids leave quote empty.")
    out = llm.generate_json("bull_bear", prompt, BB_SCHEMA, model=llm.REASON, thinking="medium",
                            ref_type="company", ref_id=symbol)
    cites: dict[str, dict] = {}
    dropped = 0

    stats_dropped = 0

    def keep(points: list[dict]) -> list[dict]:
        nonlocal dropped, stats_dropped
        res = []
        for p in points:
            ids, support = [], []
            for r in p.get("refs", []):
                rid = r["id"].strip("[] ")
                if rid in nrefs:
                    cites.setdefault(rid, number_citation(rid, nrefs[rid]))
                    ids.append(rid)
                    support.append(nrefs[rid])
                elif rid in crefs and quote_in(r.get("quote", ""), crefs[rid].content):
                    cites.setdefault(rid, citation(rid, crefs[rid], r["quote"]))
                    ids.append(rid)
                    support.append(crefs[rid].content)
                else:
                    dropped += 1
            if not ids:
                continue
            # The headline stat must be backed by what this point cites; otherwise show no stat.
            stat = (p.get("stat") or "").strip()
            if stat and (not re.search(r"\d", stat) or not _numbers_ok(stat, " ".join(support))):
                stats_dropped += 1
                stat = ""
            res.append({"title": (p.get("title") or "").strip()[:48], "stat": stat[:40], "point": p["point"],
                        "citation_ids": sorted(set(ids))})
        return res[:3]

    content = {"bull": keep(out.get("bull", [])), "bear": keep(out.get("bear", [])),
               "basis": "numbers + documents" if chunks else "numbers only (no documents uploaded)",
               "verification": {"dropped_refs": dropped, "stats_dropped": stats_dropped}}
    return _env("bull_bear", "ready", llm.REASON, content, list(cites.values()))


# ------------------------------------------------------------- cache/glue
def _env(section: str, status: str, model: str | None, content: dict, citations: list[dict]) -> dict:
    return {"section": section, "status": status, "model": model,
            "generated_at": datetime.now(timezone.utc).isoformat(), "content": content, "citations": citations}


_BUILDERS = {"snapshot": snapshot, "health": health, "promise_delivered": promise_delivered, "bull_bear": bull_bear}


def inputs_hash(symbol: str, section: str) -> str:
    with cursor(commit=False) as c:
        c.execute("select md5(tables::text) from public.fundamentals where symbol = %s", (symbol,))
        r = c.fetchone()
        c.execute("select coalesce(string_agg(sha256, ',' order by sha256), '') from public.documents "
                  "where symbol = %s", (symbol,))
        docs = c.fetchone()[0]
    return hashlib.sha256(f"{SECTION_VERSION.get(section, VERSION)}|{section}|{r[0] if r else ''}|{docs}".encode()).hexdigest()


def get_section(symbol: str, section: str, force: bool = False) -> dict:
    if section not in _BUILDERS:
        raise ValueError(f"Unknown section {section}")
    h = inputs_hash(symbol, section)
    if not force:
        with cursor(commit=False) as c:
            c.execute("select content from public.dossier_sections where symbol = %s and section = %s and "
                      "inputs_hash = %s", (symbol, section, h))
            hit = c.fetchone()
        if hit:
            env = hit[0] if isinstance(hit[0], dict) else json.loads(hit[0])
            return {**env, "cached": True}
    try:
        env = _BUILDERS[section](symbol)
    except Exception as e:
        return _env(section, "error", None, {"error": f"{type(e).__name__}: {str(e)[:200]}"}, [])
    if env["status"] != "error":
        with cursor() as c:
            c.execute("""insert into public.dossier_sections (symbol, section, inputs_hash, content, model)
                         values (%s, %s, %s, %s::jsonb, %s)
                         on conflict (symbol, section, inputs_hash) do update set content = excluded.content,
                           model = excluded.model, created_at = now()""",
                      (symbol, section, h, json.dumps(env), env["model"]))
    return {**env, "cached": False}


def invalidate(symbol: str) -> None:
    with cursor() as c:
        c.execute("delete from public.dossier_sections where symbol = %s", (symbol,))
