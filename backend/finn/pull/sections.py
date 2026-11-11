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
from finn.pull.cite import chunk_block, citation, number_citation, quote_in
from finn.pull.retrieve import Chunk, documents, search
from finn.push.results import build_card, quarter_label

VERSION = "v1"
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


def _business(symbol: str, name: str) -> tuple[dict | None, list[dict], dict]:
    chunks = search(symbol, "business overview what the company does segments products services revenue mix "
                            "customers geographies", k=8)
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
        ch = refs.get(cite)
        if ch and quote_in(quote, ch.content):
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
        "verdict": {"type": "string", "enum": ["hit", "partial", "missed", "pending", "unverifiable"]},
        "actual": {"type": "string"}, "explanation": {"type": "string"}},
        "required": ["id", "verdict", "actual", "explanation"]}}},
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


def promise_delivered(symbol: str) -> dict:
    f = _fund(symbol)
    transcripts = [d for d in documents(symbol) if d["kind"] == "transcript"][:4]
    if not transcripts:
        return _env("promise_delivered", "needs_docs", None,
                    {"reason": "Upload the last 4 concall transcripts to compare guidance with delivery.",
                     "score": None, "items": []}, [])
    promises, cites, dropped = [], {}, 0
    for d in transcripts:
        chunks: list[Chunk] = []
        seen = set()
        for q in ("guidance outlook we expect target growth for the year", "margin band EBITDA margin expect range",
                  "capex investment capacity plan crore"):
            for ch in search(symbol, q, k=5, document_ids=[d["id"]]):
                if ch.chunk_id not in seen:
                    seen.add(ch.chunk_id)
                    chunks.append(ch)
        if not chunks:
            continue
        block, refs = chunk_block(chunks)
        prompt = (f"Company: {f['name']}. Source: {d['label']} transcript.\n{PRIMARY_ONLY}\n\nExcerpts:\n{block}\n\n"
                  "List explicit, quantifiable forward-looking statements made by MANAGEMENT (not analysts' "
                  "questions) about headline numbers: revenue or volume growth, margins, profit growth, capex, or "
                  "other numeric targets. Skip vague optimism. Max 5. For each: the excerpt id and a VERBATIM quote "
                  "(10-35 words) copied exactly from it; target_period like 'FY27', 'Q3 FY27', 'next 2-3 years'.")
        out = llm.generate_json("promise_extract", prompt, PROMISE_SCHEMA, model=llm.BULK, thinking="low",
                                ref_type="document", ref_id=str(d["id"]))
        for p in out.get("promises", []):
            ch = refs.get(p["cite"])
            if not ch or not quote_in(p["quote"], ch.content):
                dropped += 1
                continue
            cid = f"c{len(cites) + 1}"
            cites[cid] = citation(cid, ch, p["quote"])
            promises.append({**p, "said_in": d["label"], "citation_id": cid})
    promises = promises[:12]
    if not promises:
        return _env("promise_delivered", "ready", llm.BULK,
                    {"score": {k: 0 for k in ("hit", "partial", "missed", "pending", "unverifiable")},
                     "items": [], "note": "No explicit quantified guidance found in the uploaded transcripts.",
                     "verification": {"dropped_quotes": dropped}}, list(cites.values()))

    actuals = _actuals_table(f["tables"])
    plist = "\n".join(f"p{i + 1}: [{p['said_in']}] {p['metric']}: {p['statement']} | target: {p['target']} | "
                      f"period: {p['target_period']}" for i, p in enumerate(promises))
    prompt = (f"Company: {f['name']}.\n{PRIMARY_ONLY}\n\nMANAGEMENT PROMISES\n{plist}\n\nREPORTED NUMBERS\n{actuals}\n\n"
              "For each promise decide: hit (delivered at/above target), partial (close or part-delivered), missed, "
              "pending (target period not fully reported yet), or unverifiable (no matching reported metric, e.g. "
              "segment or volume data not in the table). 'actual' must quote numbers ONLY from REPORTED NUMBERS "
              "(or be 'n/a'). explanation <= 30 words, plain and specific.")
    out = llm.generate_json("promise_verdict", prompt, VERDICT_SCHEMA, model=llm.REASON, thinking="medium",
                            ref_type="company", ref_id=symbol)
    by_id = {a["id"]: a for a in out.get("assessments", [])}
    items, guarded = [], 0
    for i, p in enumerate(promises):
        a = by_id.get(f"p{i + 1}") or {"verdict": "unverifiable", "actual": "n/a", "explanation": "Not assessed."}
        verdict, actual, expl = a["verdict"], a["actual"], a["explanation"]
        if not _numbers_ok(actual, actuals + " " + p["target"]):
            guarded += 1
            verdict, actual, expl = "unverifiable", "n/a", "Could not match the claimed actual to reported numbers."
        items.append({"promise": p["statement"], "said_in": p["said_in"], "metric": p["metric"], "target": p["target"],
                      "target_period": p["target_period"], "actual": actual, "verdict": verdict, "explanation": expl,
                      "citation_id": p["citation_id"]})
    score = {k: sum(1 for x in items if x["verdict"] == k) for k in ("hit", "partial", "missed", "pending",
                                                                       "unverifiable")}
    return _env("promise_delivered", "ready", llm.REASON,
                {"score": score, "items": items, "transcripts_used": [d["label"] for d in transcripts],
                 "verification": {"dropped_quotes": dropped, "actuals_guarded": guarded}}, list(cites.values()))


# ---------------------------------------------------------------- bull/bear
BB_POINT = {"type": "object", "properties": {
    "point": {"type": "string"},
    "refs": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["id", "quote"]}}},
    "required": ["point", "refs"]}
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
              + "Write a tight bull case and bear case: exactly 3 points each, each <= 25 words, specific, no hype. "
                "Every point must cite at least one id from NUMBER FACTS (n#) or DOCUMENT EXCERPTS (c#). For c# ids "
                "include a VERBATIM quote (8-30 words) copied exactly from that excerpt; for n# ids leave quote empty.")
    out = llm.generate_json("bull_bear", prompt, BB_SCHEMA, model=llm.REASON, thinking="medium",
                            ref_type="company", ref_id=symbol)
    cites: dict[str, dict] = {}
    dropped = 0

    def keep(points: list[dict]) -> list[dict]:
        nonlocal dropped
        res = []
        for p in points:
            ids = []
            for r in p.get("refs", []):
                rid = r["id"].strip("[] ")
                if rid in nrefs:
                    cites.setdefault(rid, number_citation(rid, nrefs[rid]))
                    ids.append(rid)
                elif rid in crefs and quote_in(r.get("quote", ""), crefs[rid].content):
                    cites.setdefault(rid, citation(rid, crefs[rid], r["quote"]))
                    ids.append(rid)
                else:
                    dropped += 1
            if ids:
                res.append({"point": p["point"], "citation_ids": sorted(set(ids))})
        return res[:3]

    content = {"bull": keep(out.get("bull", [])), "bear": keep(out.get("bear", [])),
               "basis": "numbers + documents" if chunks else "numbers only (no documents uploaded)",
               "verification": {"dropped_refs": dropped}}
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
    return hashlib.sha256(f"{VERSION}|{section}|{r[0] if r else ''}|{docs}".encode()).hexdigest()


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
