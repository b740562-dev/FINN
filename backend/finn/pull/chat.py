"""Surya: a conversational investment guide.

Two kinds of answer, and the line between them is enforced in code:
  * General guidance (how to judge debt, why diversify, what a concall is):
    allowed, no citations needed, but no company-specific figures.
  * Anything about a specific company's data: only from that company's verified
    material in FINN: its own documents (annual reports, concall transcripts,
    presentations, including user uploads) and the financials it reported to the
    exchange. Every such claim carries an inline [c#]/[n#] marker whose quote is
    checked against the source; numbers must appear in the cited material.
    Otherwise Surya says it doesn't have it and asks for the matching report.
"""
from __future__ import annotations

import re

from finn import llm
from finn.db import cursor
from finn.pull.cite import citation, number_citation, quote_in
from finn.pull.retrieve import documents, search
from finn.pull.sections import number_facts
from finn.push.classify import numbers_grounded

GREETING = "Hello, I’m Surya, your investment guide. What decision can I help you with today?"
MAX_COMPANIES = 2

SYSTEM = (
    "You are Surya, a calm, plain-spoken investment guide inside FINN, an app for Indian retail investors. "
    "Two strict rules:\n"
    "1. GENERAL guidance (concepts, how to evaluate something, risk, diversification, what to look for) is "
    "allowed from your own knowledge. Keep it practical. Never give a buy/sell/hold call or a price target; "
    "help the user think instead.\n"
    "2. COMPANY DATA (any figure, result, guidance, statement, event, ratio or fact about a specific company) "
    "may ONLY come from the VERIFIED MATERIAL section, cited inline with its marker like [c2], [n1] or [g1]. "
    "Never use outside or remembered knowledge about a company. If the user asks for company data that the "
    "verified material does not contain (or no material is given for that company), set kind=\"missing\", "
    "say plainly you don't have it in a verified document yet, and name the report that would answer it "
    "(e.g. the latest annual report or concall transcript) in missing_report.\n"
    "Style: short paragraphs or a few bullets, <= 150 words, no headings, rupee amounts as ₹ … cr."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["general", "company_data", "missing"]},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["id", "quote"]}},
        "missing_report": {"type": "string"},
    },
    "required": ["kind", "answer", "citations"],
}

_SUFFIX = re.compile(r"\b(ltd|limited|company|co|corporation|corp|industries|india|of|the|and|&)\b\.?", re.I)


def _core(name: str) -> str:
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", name or "")).strip().lower()


def _aliases() -> list[tuple[str, str, re.Pattern, str]]:
    """(symbol, name, pattern, short) for every company FINN knows: symbol, full
    name, and the name's first word ("Titan", "Reliance") when no other company
    shares it. `short` is that first word, '' if not used."""
    with cursor(commit=False) as c:
        c.execute("select symbol, name from public.companies")
        rows = c.fetchall()
    firsts: dict[str, int] = {}
    for _, name in rows:
        f = _core(name).split(" ")[0]
        firsts[f] = firsts.get(f, 0) + 1
    out = []
    for sym, name in rows:
        alts, core, short = {sym.lower()}, _core(name), ""
        if len(core) >= 3:
            alts.add(core)
            first = core.split(" ")[0]
            if len(first) >= 4 and firsts.get(first) == 1 and first != core:
                alts.add(first)
                short = first
        pat = re.compile(r"\b(" + "|".join(sorted((re.escape(a) for a in alts), key=len, reverse=True)) + r")\b", re.I)
        out.append((sym, name, pat, short))
    return out


def detect_companies(text: str, limit: int = MAX_COMPANIES) -> list[dict]:
    """Companies named in the text, most specific (longest) match first. A bare
    first word doesn't count when the user goes on to name a different company
    ("Adani Green" is not Adani Enterprises)."""
    hits = []
    text = text or ""
    for sym, name, pat, short in _aliases():
        m = pat.search(text)
        if not m:
            continue
        if short and m.group(0).lower() == short:
            nxt = re.match(r"\s+([A-Z][A-Za-z]+)", text[m.end():])
            if nxt and nxt.group(1).lower() not in _core(name).split(" ")[1:2]:
                continue
        hits.append((len(m.group(0)), m.start(), sym, name))
    hits.sort(key=lambda h: (-h[0], h[1]))
    seen, out = set(), []
    for _, _, sym, name in hits:
        if sym not in seen:
            seen.add(sym)
            out.append({"symbol": sym, "name": name})
    return out[:limit]


_BOILER = re.compile(r"dear sir|security code|phiroze|exchange plaza|listing department|bandra kurla|"
                     r"retires? by rotation|notice is hereby|special business|scrip code|kind attn|"
                     r"pursuant to regulation 30", re.I)
_STOPQ = re.compile(r"\b(what|did|does|do|is|are|was|were|the|a|an|of|in|on|for|about|say|said|tell|me|please|"
                    r"management|company|its|their|they|last|latest|recent|concall|call|transcript|annual|report)\b",
                    re.I)


def _retrieve(sym: str, name: str, message: str, docs: list[dict], k: int = 6):
    """Topic-focused retrieval: strip the company's name and question words from
    the query, narrow to the latest concall / annual report when asked, and drop
    exchange cover letters and notice boilerplate that otherwise win on vague asks."""
    topic = message
    for w in {sym, *_core(name).split(" ")}:
        if len(w) >= 3:
            topic = re.sub(rf"\b{re.escape(w)}('s)?\b", " ", topic, flags=re.I)
    topic = re.sub(r"\s+", " ", _STOPQ.sub(" ", topic)).strip(" ?.,") or message
    low = message.lower()
    kind = ("transcript" if re.search(r"concall|earnings call|conference call|transcript|\bcall\b", low)
            else "annual_report" if "annual report" in low else None)
    ids = None
    if kind and re.search(r"\b(last|latest|recent)\b", low):
        same = [d for d in docs if d["kind"] == kind]
        if same:
            ids = [max(same, key=lambda d: d["period"] or "")["id"]]
    pool = search(sym, topic, k=k * 3, kind=kind, document_ids=ids)
    good = [ch for ch in pool if not _BOILER.search(ch.content[:600]) and len(ch.content) > 200]
    return (good or pool)[:k]


_GUIDANCE = re.compile(r"guidance|guide|target|promise|outlook|commit|deliver|\bhit\b|\bmiss", re.I)


def _guidance_lines(sym: str) -> list[tuple[str, dict]]:
    """Promise vs Delivered items (already verified against the transcripts and
    the reported numbers) as citable lines, only if that section is built."""
    from finn.pull import sections as S
    try:
        sec = S.get_section(sym, "promise_delivered")
    except Exception:
        return []
    if sec.get("status") != "ready":
        return []
    by_id = {c["id"]: c for c in sec.get("citations", [])}
    out = []
    for it in sec["content"].get("items", [])[:10]:
        cite = by_id.get(it.get("citation_id") or "")
        if not cite:
            continue
        line = (f"Said in {it.get('said_in')}: \"{it.get('promise')}\" Target: {it.get('target')} "
                f"({it.get('target_period')}). Status: {it.get('verdict')}. Actual so far: {it.get('actual')}. "
                f"{it.get('explanation') or ''}")
        out.append((line, cite))
    return out


def _missing_text(companies: list[dict], report: str | None) -> str:
    who = " / ".join(c["name"] for c in companies) if companies else "that company"
    what = report or "its latest annual report or concall transcript"
    return (f"I don’t have that in a verified document for {who} yet. Add the matching report ({what}) "
            "with the 📎 button and I’ll analyse it for you.")


def chat(message: str, history: list[dict] | None = None, symbols: list[str] | None = None) -> dict:
    message = message.strip()[:800]
    history = [h for h in (history or []) if h.get("role") in ("user", "assistant")][-6:]

    # Which companies is this about? Explicit chips first, then the message, then recent turns.
    companies = [{"symbol": s.upper(), "name": s.upper()} for s in (symbols or [])][:MAX_COMPANIES]
    if not companies:
        companies = detect_companies(message)
    if not companies:
        companies = detect_companies(" ".join(h.get("content", "") for h in history[-2:] if h["role"] == "user"))

    material, nrefs, crefs, grefs, inventory = [], {}, {}, {}, []
    nsym: dict[str, str] = {}
    for co in companies:
        sym = co["symbol"]
        docs = documents(sym)
        labels = sorted({d["label"] for d in docs if d.get("label")})
        inventory.append({"symbol": sym, "name": co["name"], "documents": labels})
        try:
            facts = number_facts(sym)
        except Exception:
            facts = []
        start = len(nrefs)
        for i, f in enumerate(facts):
            nrefs[f"n{start + i + 1}"] = f"{co['name']}: {f}"
            nsym[f"n{start + i + 1}"] = sym
        for ch in (_retrieve(sym, co["name"], message, docs) if docs else []):
            crefs[f"c{len(crefs) + 1}"] = ch          # ids unique across companies
        gstart = len(grefs)
        if docs and _GUIDANCE.search(message):
            for line, cite in _guidance_lines(sym):
                gid = f"g{len(grefs) + 1}"
                grefs[gid] = (f"{co['name']}: {line}", {**cite, "id": gid})
        material.append(
            f"### {co['name']} ({sym})\nDocuments on file: {', '.join(labels) or 'none'}\n"
            + "\n".join(f"[{k}] {v}" for k, v in list(nrefs.items())[start:])
            + ("\nGUIDANCE TRACKER (management promises checked against reported numbers)\n"
               + "\n".join(f"[{k}] {v[0]}" for k, v in list(grefs.items())[gstart:]) if len(grefs) > gstart else "")
        )
    if crefs:
        block = "\n\n".join(f"[{r}] ({ch.doc_label}, p.{ch.page})\n{ch.content}" for r, ch in crefs.items())
        material.append("DOCUMENT EXCERPTS\n" + block)

    convo = "\n".join(f"{'User' if h['role'] == 'user' else 'Surya'}: {h.get('content', '')[:600]}" for h in history)
    prompt = (
        "VERIFIED MATERIAL\n" + ("\n\n".join(material) if material else "(none: no specific company in this question)")
        + (f"\n\nCONVERSATION SO FAR\n{convo}" if convo else "")
        + f"\n\nUSER: {message}\n\n"
        "Reply as Surya. For every c# you cite, give a VERBATIM quote (8-30 words) copied exactly from that "
        "excerpt; for n# and g# leave the quote empty. kind=general if no company data is used."
    )
    out = llm.generate_json("chat", prompt, SCHEMA, model=llm.REASON, system=SYSTEM, thinking="low",
                            temperature=0.3, ref_type="chat", ref_id=",".join(c["symbol"] for c in companies) or None)

    kind = out.get("kind", "general")
    answer = (out.get("answer") or "").strip()
    # "[c2, c4]" -> "[c2][c4]" so every marker is checked (and stripped) on its own
    answer = re.sub(r"\[((?:[cng]\d+\s*,\s*)+[cng]\d+)\]",
                    lambda m: "".join(f"[{x.strip()}]" for x in m.group(1).split(",")), answer)
    cites, dropped = [], 0
    for c in out.get("citations", []):
        rid = c.get("id", "").strip("[] ")
        if rid in nrefs:
            cites.append(number_citation(rid, nrefs[rid]))
        elif rid in grefs:                         # already verified when the tracker was built
            cites.append(grefs[rid][1])
        elif rid in crefs and quote_in(c.get("quote", ""), crefs[rid].content):
            cites.append(citation(rid, crefs[rid], c["quote"]))
        else:
            dropped += 1
    valid = {c["id"] for c in cites}
    answer = re.sub(r"\s?\[([cng]\d+)\]", lambda m: m.group(0) if m.group(1) in valid else "", answer)

    # Guard: company-specific numbers must come from the material actually cited.
    guard = None
    if companies and kind != "missing":
        cited_text = " ".join([nrefs[i] for i in valid if i in nrefs]
                              + [f"{grefs[i][0]} {grefs[i][1].get('quote', '')}" for i in valid if i in grefs]
                              + [f"{crefs[i].doc_label} {crefs[i].content}" for i in valid if i in crefs]
                              + [lb for inv in inventory for lb in inv["documents"]])
        # PDF text layers split numbers ("72 , 000 crores", "1 , 600"): rejoin before comparing
        cited_text = re.sub(r"(?<=\d)\s*,\s*(?=\d{2,3}\b)", ",", cited_text)
        cited_text = re.sub(r"(?<=\d)\s+\.\s*(?=\d)", ".", cited_text)
        if not numbers_grounded(re.sub(r"\[[cng]\d+\]", "", answer), cited_text):
            guard = "ungrounded_numbers"
        elif kind == "company_data" and not cites:
            guard = "no_valid_citations"
    if kind == "missing" or guard:
        answer, cites, kind = _missing_text(companies, out.get("missing_report")), [], "missing"

    cites = _with_sources(list({c["id"]: c for c in cites}.values()), nsym)
    # "Verified": a company answer with figures, every one of which passed the
    # number check against sources the user can open.
    verified = kind == "company_data" and bool(re.search(r"\d", re.sub(r"\[[cng]\d+\]", "", answer))) \
        and bool(cites) and all(c.get("url") for c in cites)
    return {"answer": answer, "kind": kind, "citations": cites, "verified": verified,
            "companies": inventory, "verification": {"dropped_refs": dropped, "guard": guard},
            "model": llm.REASON}


def _with_sources(cites: list[dict], nsym: dict[str, str]) -> list[dict]:
    """Attach a link to the original for every citation: the exchange PDF a
    document came from (opened at the cited page), or the company's financials
    page for reported numbers."""
    doc_ids = [c["doc_id"] for c in cites if c.get("doc_id")]
    urls: dict[int, str] = {}
    if doc_ids:
        with cursor(commit=False) as c:
            c.execute("select id, source_url from public.documents where id = any(%s::bigint[])", (doc_ids,))
            urls = {i: u for i, u in c.fetchall() if u}
    out = []
    for c in cites:
        c = dict(c)
        if c.get("doc_id") and c["doc_id"] in urls:
            base = urls[c["doc_id"]]
            c["url"] = f"{base}#page={c['page']}" if c.get("page") and ".pdf" in base.lower() else base
        elif c["id"] in nsym:
            sym = nsym[c["id"]]
            with cursor(commit=False) as cur:
                cur.execute("select basis from public.companies where symbol = %s", (sym,))
                r = cur.fetchone()
            c["url"] = f"https://www.screener.in/company/{sym}/" + ("consolidated/" if r and r[0] == "consolidated" else "")
            c["doc_label"] = "Reported financials"
        out.append(c)
    return out
