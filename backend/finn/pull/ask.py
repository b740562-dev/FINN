"""Follow-up questions on a company, answered only from its own documents
and its reported numbers, with verified inline citations."""
from __future__ import annotations

import re

from finn import llm
from finn.pull.cite import chunk_block, citation, number_citation, quote_in
from finn.pull.retrieve import search
from finn.pull.sections import PRIMARY_ONLY, _fund, number_facts

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["id", "quote"]}},
    },
    "required": ["found", "answer", "citations"],
}


def ask(symbol: str, question: str) -> dict:
    question = question.strip()[:500]
    f = _fund(symbol)
    facts = number_facts(symbol)
    nrefs = {f"n{i + 1}": x for i, x in enumerate(facts)}
    chunks = search(symbol, question, k=8)
    block, crefs = chunk_block(chunks)
    prompt = (f"Company: {f['name']}.\n{PRIMARY_ONLY}\n\nNUMBER FACTS\n"
              + "\n".join(f"[{k}] {v}" for k, v in nrefs.items())
              + (f"\n\nDOCUMENT EXCERPTS\n{block}" if chunks else "\n\n(No documents uploaded for this company.)")
              + f"\n\nQUESTION: {question}\n\n"
                "Answer in <= 120 words, plain English, specific numbers where available. Put inline markers like "
                "[c2] or [n1] after each claim. In citations, for each c# you used give a VERBATIM quote (8-30 "
                "words) copied exactly from that excerpt; for n# leave quote empty. If the material doesn't answer "
                "the question, set found=false and say what is missing.")
    out = llm.generate_json("ask", prompt, SCHEMA, model=llm.REASON, thinking="medium", ref_type="company",
                            ref_id=symbol)
    cites, bad = [], set()
    for c in out.get("citations", []):
        rid = c["id"].strip("[] ")
        if rid in nrefs:
            cites.append(number_citation(rid, nrefs[rid]))
        elif rid in crefs and quote_in(c.get("quote", ""), crefs[rid].content):
            cites.append(citation(rid, crefs[rid], c["quote"]))
        else:
            bad.add(rid)
    answer = out.get("answer", "")
    valid = {c["id"] for c in cites}
    # strip markers that point at unverified or unknown refs
    answer = re.sub(r"\s?\[([cn]\d+)\]", lambda m: m.group(0) if m.group(1) in valid else "", answer)
    dedup = {c["id"]: c for c in cites}
    return {"answer": answer, "found": bool(out.get("found")), "citations": list(dedup.values()),
            "model": llm.REASON, "verification": {"dropped_refs": len(bad)},
            "sources_searched": len(chunks)}
