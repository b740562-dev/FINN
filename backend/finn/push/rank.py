"""Per-user digest: group duplicate filings into events, score them for this
user's portfolio, and split into "what matters" vs collapsed routine.

score = filing materiality (global, computed once per filing)
      + 10 if the category is one the user cares about
      + position weight (% of book, capped at 10)
Routine (materiality < ROUTINE_BELOW) is collapsed regardless of score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from finn.db import cursor
from finn.push.classify import ROUTINE_BELOW

GROUP_WINDOW = timedelta(hours=72)

LABEL = {
    "results": "Results", "M&A": "M&A", "fund_raise": "Fund raise", "management_change": "Management",
    "litigation": "Legal", "insider_trading": "Insider", "earnings_call": "Concall", "investor_meetings":
    "Investor meet", "credit_rating": "Rating", "dividend": "Dividend", "bonus_split": "Bonus/split",
    "capex": "Capex", "press_release": "Update", "report": "Report", "postal_ballot": "Postal ballot", "agm_egm": "AGM/EGM",
    "pledging": "Pledge", "unclassified": "Routine",
}


@dataclass
class Event:
    symbol: str
    company: str
    category: str
    filed_at: datetime
    materiality: int
    headline: str
    one_liner: str | None
    url: str | None
    factors: list[str]
    enrichment: dict
    filing_ids: list[int] = field(default_factory=list)
    related: int = 0
    score: float = 0.0
    why: str = ""
    weight: float = 0.0

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["filed_at"] = self.filed_at.isoformat()
        d["label"] = LABEL.get(self.category, self.category)
        return d


def _group(rows: list[dict]) -> list[Event]:
    """Merge filings of the same company + category within 72h (e.g. a results
    board outcome, media statement and shareholder letter -> one event).
    The most material filing leads the event."""
    rows = sorted(rows, key=lambda r: (r["symbol"], r["category"], r["filed_at"]))
    events: list[Event] = []
    for r in rows:
        last = events[-1] if events else None
        if (last and last.symbol == r["symbol"] and last.category == r["category"]
                and abs(r["filed_at"] - last.filed_at) <= GROUP_WINDOW):
            last.related += 1
            last.filing_ids.append(r["id"])
            better = r["materiality"] > last.materiality or (
                r["materiality"] == last.materiality and bool(r["one_liner"]) and not last.one_liner)
            if better:
                last.materiality, last.headline, last.one_liner = r["materiality"], r["subject"], r["one_liner"]
                last.url, last.factors, last.enrichment = r["url"], r["factors"], r["enrichment"]
            last.filed_at = max(last.filed_at, r["filed_at"])
            continue
        events.append(Event(
            symbol=r["symbol"], company=r["company"], category=r["category"], filed_at=r["filed_at"],
            materiality=r["materiality"], headline=r["subject"], one_liner=r["one_liner"], url=r["url"],
            factors=r["factors"], enrichment=r["enrichment"], filing_ids=[r["id"]]))
    return events


def build_digest(holdings: dict[str, float], care_categories: list[str], *,
                 since: datetime, until: datetime | None = None) -> dict:
    """holdings: {symbol: weight%}. Returns {'matters': [...], 'routine': [...], 'counts': {...}}."""
    until = until or datetime.now(timezone.utc)
    with cursor(commit=False) as c:
        c.execute(
            """select f.id, f.symbol, co.name, f.filed_at, f.subject, f.one_liner, f.url, f.category,
                      coalesce(f.materiality, 0), coalesce(f.enrichment, '{}'::jsonb)
               from public.filings f join public.companies co using (symbol)
               where f.symbol = any(%s::text[]) and f.filed_at >= %s and f.filed_at < %s
                 and f.category is not null""",
            (list(holdings), since, until),
        )
        rows = []
        for fid, sym, name, ts, subj, one, url, cat, mat, enr in c.fetchall():
            enr = enr if isinstance(enr, dict) else json.loads(enr)
            rows.append(dict(id=fid, symbol=sym, company=name, filed_at=ts, subject=subj, one_liner=one, url=url,
                             category=cat, materiality=int(mat), enrichment=enr, factors=enr.get("factors", [])))

    events = _group(rows)
    care = set(care_categories)
    for e in events:
        e.weight = holdings.get(e.symbol, 0.0)
        e.score = e.materiality + (10 if e.category in care else 0) + min(e.weight, 10)
        parts = [LABEL.get(e.category, e.category), f"{round(e.weight, 1):g}% of book"]
        if e.factors:
            parts.append(e.factors[0])
        e.why = " · ".join(parts)

    matters = sorted([e for e in events if e.materiality >= ROUTINE_BELOW], key=lambda e: (-e.score, e.filed_at))
    routine = sorted([e for e in events if e.materiality < ROUTINE_BELOW], key=lambda e: e.filed_at, reverse=True)
    routine_mix: dict[str, int] = {}
    for e in routine:
        routine_mix[LABEL.get(e.category, e.category)] = routine_mix.get(LABEL.get(e.category, e.category), 0) + 1 + e.related
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "counts": {"filings": len(rows), "events": len(events), "matters": len(matters),
                   "routine_filings": sum(1 + e.related for e in routine)},
        "routine_mix": dict(sorted(routine_mix.items(), key=lambda kv: -kv[1])),
        "matters": [e.to_dict() for e in matters],
        "routine": [e.to_dict() for e in routine],
    }
