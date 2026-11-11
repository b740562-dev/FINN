"""Management-change enrichment: who is the incoming person?

For each person *joining* (or changing into) a role in a management_change
filing:
 1. One web search (Tavily), cached, so re-runs are free.
 2. One BULK-model call turns the search snippets into a short bio, using
    ONLY those snippets + the filing text, and says whether the snippets
    are really about this person.
 3. Grounding check in code: every organisation / school / proper noun in
    the bio must appear in the snippets or filing text, else it is dropped.
Bios carry their source links. Web enrichment is push-side only; the pull
(research) side never uses web data.

Usage: python -m finn.push.bios [--all]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys

import requests

from finn import config, llm
from finn.db import cursor

TAVILY_URL = "https://api.tavily.com/search"


def tavily(query: str, max_results: int = 6) -> list[dict]:
    key = "tavily:" + hashlib.sha256(f"{query}|{max_results}".encode()).hexdigest()
    with cursor(commit=False) as c:
        c.execute("select response from public.llm_cache where key = %s", (key,))
        hit = c.fetchone()
    if hit:
        res = hit[0] if not isinstance(hit[0], str) else json.loads(hit[0])
        return res["results"]
    r = requests.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {config.env('TAVILY_API_KEY')}", "Content-Type": "application/json"},
        json={"query": query, "search_depth": "basic", "max_results": max_results, "include_answer": False},
        timeout=30,
    )
    r.raise_for_status()
    results = [{"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("content", "")}
               for x in r.json().get("results", [])]
    with cursor() as c:
        c.execute("insert into public.llm_cache (key, model, response) values (%s, 'tavily', %s::jsonb) "
                  "on conflict (key) do nothing", (key, json.dumps({"query": query, "results": results})))
    return results


SYSTEM = """You write a short professional background for a person newly appointed at an Indian listed company.
Use ONLY the numbered search snippets and the filing text provided. Never add facts from your own knowledge.
If the snippets do not clearly describe this same person (same name AND consistent with the company/role),
set same_person to "no" or "unsure" and leave the other fields empty.
- headline: <= 14 words, the single most useful fact about where they come from (e.g. "Ex-MD & CEO of X; 30 years at Y").
- summary: <= 45 words, career path in plain English, most relevant first.
- prior_roles: organisations and roles stated in the snippets.
- education: degrees/schools stated in the snippets.
- sources: snippet numbers you used."""

SCHEMA = {
    "type": "object",
    "properties": {
        "same_person": {"type": "string", "enum": ["yes", "unsure", "no"]},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "prior_roles": {"type": "array", "items": {"type": "object", "properties": {
            "org": {"type": "string"}, "role": {"type": "string"}}, "required": ["org", "role"]}},
        "education": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["same_person", "headline", "summary", "prior_roles", "education", "sources"],
}

_STOP = {"The", "And", "For", "With", "Ex", "Former", "Formerly", "Group", "Head", "Chief", "Officer", "Executive",
         "Managing", "Director", "Chairman", "Chairperson", "Independent", "Non", "Vice", "President", "Board",
         "Bank", "Limited", "Ltd", "India", "Indian", "Years", "Year", "Over", "Joined", "Served", "Also", "Has",
         "He", "She", "They", "His", "Her", "Their", "Prior", "Before", "Most", "Recently", "Currently", "MD", "CEO",
         "CFO", "COO", "CTO", "Since", "From", "At", "In", "Of", "On", "As", "A", "An"}


def _grounded(text: str, corpus: str) -> bool:
    """Every capitalised word / acronym in `text` must appear in the corpus."""
    low = corpus.lower()
    for w in re.findall(r"\b[A-Z][A-Za-z&.'-]{1,}\b", text or ""):
        w = w.strip(".'-")
        if w in _STOP or len(w) < 2:
            continue
        if w.lower() not in low:
            return False
    return True


_WEAK_SOURCES = ("instagram.com", "facebook.com", "twitter.com", "x.com", "baidu.com", "threads.net",
                 "youtube.com", "pinterest.", "quora.com", "reddit.com")
_SENIOR = re.compile(r"chief executive|\bceo\b|managing director|\bmd\b|chair|president|founder|senior partner|"
                     r"executive director|\bcfo\b|chief financial", re.I)


def _short_role(role: str) -> str:
    r = re.sub(r"managing director", "MD", role, flags=re.I)
    r = re.sub(r"chief executive officer", "CEO", r, flags=re.I)
    r = re.sub(r"chief financial officer", "CFO", r, flags=re.I)
    return re.sub(r"\s+and\s+", " & ", r)


def _fallback_headline(roles: list[dict]) -> str:
    """Most senior grounded prior role, e.g. 'Ex-MD & CEO, ICICI Securities'."""
    if not roles:
        return ""
    best = next((r for r in roles if _SENIOR.search(r["role"])), roles[0])
    return f"Ex-{_short_role(best['role'])}, {best['org']}"


def _rank_sources(snips: list[dict], company: str) -> list[dict]:
    """Drop social/aggregator links; company site and news first."""
    first_word = company.split()[0].lower()
    keep = [s for s in snips if not any(d in s["url"].lower() for d in _WEAK_SOURCES)]
    return sorted(keep, key=lambda s: (first_word not in s["url"].lower(), "linkedin.com" in s["url"].lower()))


def bio_for(name: str, role: str, company: str, filing_text: str) -> dict:
    snippets = tavily(f"{name} {role} {company} career background profile")
    if not snippets:
        return {"name": name, "role": role, "status": "not_found"}
    numbered = "\n".join(f"[{i}] {s['title']} :: {s['content'][:700]}" for i, s in enumerate(snippets))
    prompt = (f"Person: {name}\nNew role: {role} at {company}\nFiling text: {filing_text}\n\n"
              f"Search snippets:\n{numbered}")
    out = llm.generate_json("person_bio", prompt, SCHEMA, model=llm.BULK, system=SYSTEM, thinking="low",
                            ref_type="person", ref_id=f"{company}:{name}"[:200])
    corpus = filing_text + " " + " ".join(f"{s['title']} {s['content']}" for s in snippets)

    if out["same_person"] != "yes":
        return {"name": name, "role": role, "status": "unconfirmed",
                "sources": [{"title": s["title"], "url": s["url"]} for s in snippets[:3]]}

    roles = [r for r in out["prior_roles"] if r["org"].lower() in corpus.lower()]
    edu = [e for e in out["education"] if _grounded(e, corpus)]
    dropped = (len(out["prior_roles"]) - len(roles)) + (len(out["education"]) - len(edu))
    headline_ok = _grounded(out["headline"], corpus)
    headline = out["headline"] if headline_ok else _fallback_headline(roles)
    summary = out["summary"] if _grounded(out["summary"], corpus) else ""
    used = [snippets[i] for i in out["sources"] if 0 <= i < len(snippets)] or snippets[:2]
    sources = _rank_sources(used, company) or _rank_sources(snippets, company)
    return {
        "name": name, "role": role, "status": "ready" if headline or roles else "thin",
        "headline": headline, "summary": summary, "prior_roles": roles, "education": edu,
        "sources": [{"title": s["title"], "url": s["url"]} for s in sources[:3]],
        "grounding": {"dropped_items": dropped, "summary_kept": bool(summary), "headline_model": headline_ok},
    }


def enrich_management_changes(redo: bool = False) -> dict:
    with cursor(commit=False) as c:
        c.execute("""select f.id, co.name, f.subject, coalesce(f.note, ''), f.enrichment->'people'
                     from public.filings f join public.companies co using (symbol)
                     where f.category = 'management_change' and f.materiality >= 35
                       and (%s or f.enrichment->'bios' is null)""", (redo,))
        rows = c.fetchall()
    stats = {"filings": len(rows), "people": 0, "ready": 0, "other": 0}
    for fid, company, subject, note, people in rows:
        people = people if isinstance(people, list) else json.loads(people or "[]")
        incoming = [p for p in people if p.get("change") in ("joining", "changing")]
        bios = []
        for p in incoming:
            b = bio_for(p["name"], p["role"], company, f"{subject}. {note}")
            bios.append(b)
            stats["people"] += 1
            stats["ready" if b["status"] == "ready" else "other"] += 1
        with cursor() as c:
            c.execute("update public.filings set enrichment = coalesce(enrichment, '{}'::jsonb) || "
                      "jsonb_build_object('bios', %s::jsonb) where id = %s", (json.dumps(bios), fid))
    return stats


if __name__ == "__main__":
    print(enrich_management_changes(redo="--all" in sys.argv))
