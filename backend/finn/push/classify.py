"""Filing classification + materiality.

Pipeline (cheapest first):
 1. Rules on the standardised BSE subject line -> category + base score.
    Clear routine items (newspaper ads, ESOP allotments, RTA address changes,
    investor-meet intimations) stop here: no LLM call at all.
 2. One batched BULK-model call for the rest: ambiguous subjects get a
    category; material ones get facts extracted (₹ amount, people, rating
    action, instrument) and a one-liner when it earns attention.
 3. Materiality is computed in code from those facts, sized against the
    company (order as % of TTM revenue, raise as % of market cap), and every
    adjustment is recorded as a human-readable factor for the "why" chip.

Usage: python -m finn.push.classify [--all]   (--all reclassifies everything)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

from finn import llm
from finn.db import cursor

CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]

BASE = {
    "results": 90, "M&A": 70, "fund_raise": 55, "management_change": 65, "litigation": 55,
    "insider_trading": 45, "earnings_call": 30, "investor_meetings": 10, "credit_rating": 50,
    "dividend": 40, "bonus_split": 50, "capex": 55, "press_release": 40, "postal_ballot": 20,
    "agm_egm": 20, "pledging": 70, "unclassified": 5,
}
ROUTINE_BELOW = 35  # materiality under this is collapsed in the digest


@dataclass
class RuleHit:
    category: str
    base: int
    final: bool          # True = confident & routine-or-self-explanatory: skip the LLM
    tag: str = ""        # sub-type hint, e.g. "results_primary", "order_win"


# Ordered: first match wins. (pattern, category, base, final, tag)
RULES: list[tuple[str, str, int, bool, str]] = [
    (r"newspaper (publication|advertisement)", "unclassified", 5, True, "newspaper_ad"),
    (r"scrutini[sz]er", "postal_ballot", 10, True, ""),
    # Notice that a meeting WILL happen: the decision comes in a later filing. Category from the
    # LLM, but materiality is capped (see score()).
    (r"board meeting intimation|intimation of (the )?board meeting|prior intimation", "unclassified", 25, False,
     "meeting_intimation"),
    (r"change in (the )?(corporate office )?address|registrar and share|kfin technologies", "unclassified", 3, True, "rta"),
    (r"allotment of esop|esps|grant of stock options|\besos\b", "unclassified", 5, True, "esop"),
    (r"earnings call transcript", "earnings_call", 30, True, "transcript"),
    (r"analyst ?/ ?investor meet - outcome|analyst\(s\) / investor\(s\) meet - outcome", "investor_meetings", 12, True, "meet_outcome"),
    (r"analyst|investor meet|investor conference|con\. call updates|roadshow", "investor_meetings", 10, True, "meet"),
    (r"results (issued|declared|published) by|reference to the financial results", "press_release", 40, False,
     "other_entity_results"),
    (r"investor presentation", "results", 40, True, "results_supporting"),
    (r"media statement|shareholders letter|press release.*results", "results", 60, False, "results_supporting"),
    (r"(financial )?results? (of the company )?for the quarter|unaudited financial results|audited financial results|"
     r"integrated filing \(financials\)|results for the (quarter|half)", "results", 90, False, "results_primary"),
    (r"monitoring agency|nil deviation|statement of deviation|utili[sz]ation", "fund_raise", 15, True, "monitoring"),
    (r"credit rating", "credit_rating", 50, False, ""),
    (r"bagging|receiving of order|award_of_order|receipt_of_order|order\(s\)", "press_release", 50, False, "order_win"),
    (r"acquisition|amalgamation|merger|demerger|scheme of arrangement|joint venture|restructuring|"
     r"disinvestment|divest", "M&A", 70, False, ""),
    (r"change in management|change in directorate|retirement|cessation|resignation|appointment|steps? down|"
     r"re-?designation|key managerial", "management_change", 65, False, ""),
    (r"pledge|encumbrance", "pledging", 70, False, ""),
    (r"sast|reg(ulation)?\.? ?29|reg(ulation)?\.? ?7\(2\)|insider trading", "insider_trading", 45, False, ""),
    (r"code of conduct under sebi \(pit\)|trading window", "insider_trading", 15, True, "pit_admin"),
    (r"insolvency|cirp|nclt|nclat|litigation|show cause|penalt|levied|sebi order|court|tribunal|fine\b",
     "litigation", 55, False, ""),
    (r"rumou?r verification|clarification sought|clarification", "press_release", 45, False, "clarification"),
    (r"commercial paper|\bncds?\b|non-convertible|\bqip\b|preferential|rights issue|warrants|buy-?back|"
     r"fund rais", "fund_raise", 55, False, ""),
    (r"dividend|record date", "dividend", 40, False, ""),
    (r"bonus|stock split|sub-division", "bonus_split", 50, False, ""),
    (r"capex|capacity expansion|new plant|expansion of|commissioning", "capex", 55, False, ""),
    (r"production volume|sales volume|business update|monthly", "press_release", 35, False, "monthly"),
    (r"postal ballot|postal_ballot", "postal_ballot", 20, True, ""),
    (r"\bagm\b|\begm\b|general meeting", "agm_egm", 20, True, ""),
    (r"press release|media release", "press_release", 40, False, ""),
]


def apply_rules(subject: str) -> RuleHit | None:
    s = subject.lower()
    for pat, cat, base, final, tag in RULES:
        if re.search(pat, s):
            return RuleHit(cat, base, final, tag)
    return None


# ---------------------------------------------------------------- LLM step
SYSTEM = """You classify Indian listed-company exchange filings for an investor's alert feed.
Use ONLY the text given for each filing (subject + note). Do not use outside knowledge about the company.
Categories: results, M&A, fund_raise, management_change, litigation, insider_trading, earnings_call,
investor_meetings, credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm,
pledging, unclassified (routine paperwork).
"results" means THIS company's own financial results; results of a parent, subsidiary or other entity
are press_release.
Field rules:
- amount_cr: the headline rupee amount in INR crore (1 billion INR = 100 crore; 1 million INR = 0.1 crore;
  1 lakh = 0.01 crore). null if none is stated.
- instrument: for fund_raise only: "equity" (QIP, preferential, rights, warrants) or "debt" (CP, NCD, loans).
- rating_action: for credit_rating only.
- people: for management changes, each person named, their role, whether joining or leaving, and seniority:
  "top" = CEO/MD/CFO/Chairman/Vice-Chairman, "board" = other directors, "senior" = other named executives.
- is_order_win: true if the filing reports winning an order or contract.
- one_liner: <= 20 words, plain English, lead with the concrete fact and number. Only write one if a
  portfolio investor should notice this filing; otherwise null. No hype, no "investors should".
"""

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "category": {"type": "string", "enum": CATEGORIES},
        "amount_cr": {"type": ["number", "null"]},
        "instrument": {"type": ["string", "null"], "enum": ["equity", "debt", None]},
        "rating_action": {"type": ["string", "null"],
                          "enum": ["upgrade", "downgrade", "reaffirm", "outlook_change", "new", None]},
        "people": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "role": {"type": "string"},
            "change": {"type": "string", "enum": ["joining", "leaving", "changing"]},
            "seniority": {"type": "string", "enum": ["top", "board", "senior"]}},
            "required": ["name", "role", "change", "seniority"]}},
        "is_order_win": {"type": "boolean"},
        "one_liner": {"type": ["string", "null"]},
    },
    "required": ["id", "category", "amount_cr", "instrument", "rating_action", "people", "is_order_win", "one_liner"],
}
BATCH_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": ITEM_SCHEMA}},
                "required": ["items"]}


def llm_batch(rows: list[dict]) -> dict[int, dict]:
    lines = []
    for r in rows:
        hint = f" | rule guess: {r['rule_cat']}" if r.get("rule_cat") else ""
        lines.append(f"[{r['id']}] {r['company']} | subject: {r['subject']} | note: {r['note'] or '-'}{hint}")
    prompt = "Classify each filing and extract fields. Return one item per id.\n\n" + "\n".join(lines)
    out = llm.generate_json("classify_filings", prompt, BATCH_SCHEMA, model=llm.BULK, system=SYSTEM,
                            thinking="low", ref_type="filings_batch",
                            ref_id=",".join(str(r["id"]) for r in rows)[:200])
    return {int(i["id"]): i for i in out.get("items", [])}


# ------------------------------------------------- one-liner number check
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(crore|cr\b|million|mn\b|billion|bn\b|lakh|%)?", re.I)
_UNIT = {"cr": "crore", "mn": "million", "bn": "billion"}


def _num_pairs(text: str) -> tuple[set[str], set[tuple[str, str]]]:
    nums, pairs = set(), set()
    for n, unit in _NUM.findall(text or ""):
        n = n.replace(",", "").rstrip(".")
        nums.add(n)
        if unit:
            pairs.add((n, _UNIT.get(unit.lower(), unit.lower())))
    return nums, pairs


_TO_CRORE = {"crore": 1.0, "million": 0.1, "billion": 100.0, "lakh": 0.01}


def numbers_grounded(one_liner: str, source: str) -> bool:
    """Every number in the one-liner must come from the filing text. Rupee
    amounts may be unit-converted (₹70 billion == ₹7,000 crore) but must equal
    a source amount within 0.5%; other numbers must appear verbatim."""
    src_nums, src_pairs = _num_pairs(source)
    src_crore = [float(n) * _TO_CRORE[u] for n, u in src_pairs if u in _TO_CRORE]
    for n, unit in _NUM.findall(one_liner or ""):
        n = n.replace(",", "").rstrip(".")
        u = _UNIT.get(unit.lower(), unit.lower()) if unit else ""
        if len(n) <= 1 and not u:          # "a 2-for-1", ordinals etc.: too short to judge
            continue
        if u in _TO_CRORE:
            v = float(n) * _TO_CRORE[u]
            if not any(abs(v - s) <= 0.005 * max(s, 1e-9) for s in src_crore):
                return False
            continue
        if n not in src_nums or (u and (n, u) not in src_pairs):
            return False
    return True


# ------------------------------------------------------- materiality (code)
def score(category: str, rule: RuleHit | None, x: dict, ctx: dict) -> tuple[int, list[str]]:
    """Deterministic materiality from category + extracted facts + company size."""
    base = rule.base if rule and rule.category == category else BASE[category]
    s, why = base, []
    amt = x.get("amount_cr")
    ttm_rev, mcap = ctx.get("ttm_revenue_cr"), ctx.get("market_cap_cr")

    if (x.get("is_order_win") or (rule and rule.tag == "order_win")) and amt and ttm_rev:
        pct = amt / ttm_rev * 100
        why.append(f"order = {pct:.1f}% of TTM revenue")
        s += 25 if pct >= 5 else 10 if pct >= 1 else 0 if pct >= 0.3 else -15
    if category == "fund_raise":
        if x.get("instrument") == "debt":
            s -= 10
            why.append("debt instrument")
        if amt and mcap:
            pct = amt / mcap * 100
            why.append(f"raise = {pct:.1f}% of market cap")
            s += 20 if pct >= 3 else 5 if pct >= 1 else 0 if pct >= 0.3 else -15
    if category == "M&A" and amt and mcap:
        pct = amt / mcap * 100
        why.append(f"deal = {pct:.1f}% of market cap")
        s += 20 if pct >= 5 else 5 if pct >= 1 else -15
    if category == "litigation" and amt is not None and ttm_rev:
        pct = amt / ttm_rev * 100
        if pct < 0.1:
            s -= 35
            why.append(f"amount = {pct:.4f}% of TTM revenue, immaterial" if pct < 0.01
                       else f"amount = {pct:.2f}% of TTM revenue, immaterial")
        elif pct >= 1:
            s += 20
            why.append(f"amount = {pct:.1f}% of TTM revenue")
    if category == "credit_rating":
        adj = {"downgrade": 30, "upgrade": 10, "outlook_change": 5, "reaffirm": -20, "new": 0}
        ra = x.get("rating_action")
        if ra:
            s += adj.get(ra, 0)
            why.append(f"rating {ra.replace('_', ' ')}")
    if category == "management_change":
        sen = {p.get("seniority") for p in x.get("people") or []}
        if "top" in sen:
            s += 20
            why.append("top management")
        elif "board" in sen:
            s -= 10
            why.append("board seat")
        elif "senior" in sen:
            s -= 20
            why.append("senior executive")
    if rule and rule.tag == "meeting_intimation" and s > 30:
        s = 30
        why.append("advance notice of a meeting")
    return max(0, min(100, s)), why


# ------------------------------------------------------------------ runner
def _context() -> dict[str, dict]:
    """TTM revenue and market cap per company, for sizing."""
    ctx: dict[str, dict] = {}
    with cursor(commit=False) as c:
        c.execute("select c.symbol, c.name, c.market_cap_cr, f.tables from public.companies c "
                  "left join public.fundamentals f using (symbol)")
        for sym, name, mcap, tables in c.fetchall():
            t = tables if isinstance(tables, dict) else json.loads(tables or "{}")
            q = (t.get("quarters") or {}).get("rows", {})
            rev_row = q.get("Sales") or q.get("Revenue") or []
            vals = [v for v in rev_row if v is not None][-4:]
            ctx[sym] = {"name": name, "market_cap_cr": float(mcap) if mcap else None,
                        "ttm_revenue_cr": sum(vals) if len(vals) == 4 else None}
    return ctx


def classify_pending(reclassify_all: bool = False, batch_size: int = 15) -> dict:
    ctx = _context()
    with cursor(commit=False) as c:
        c.execute("select id, symbol, subject, note from public.filings "
                  + ("" if reclassify_all else "where category is null ") + "order by id")
        rows = [dict(id=r[0], symbol=r[1], subject=r[2], note=r[3]) for r in c.fetchall()]

    stats = {"total": len(rows), "rules_only": 0, "llm": 0, "llm_calls": 0}
    results: dict[int, tuple] = {}
    to_llm: list[dict] = []
    for r in rows:
        hit = apply_rules(r["subject"])
        r["rule"] = hit
        r["rule_cat"] = hit.category if hit else None
        r["company"] = ctx.get(r["symbol"], {}).get("name", r["symbol"])
        if hit and hit.final:
            results[r["id"]] = (hit.category, hit.base, None, {"rule_tag": hit.tag, "factors": []}, "rules")
            stats["rules_only"] += 1
        else:
            to_llm.append(r)

    for i in range(0, len(to_llm), batch_size):
        chunk = to_llm[i:i + batch_size]
        extracted = llm_batch(chunk)
        stats["llm_calls"] += 1
        for r in chunk:
            x = extracted.get(r["id"])
            hit: RuleHit | None = r["rule"]
            if not x:  # model skipped it: fall back to the rule (or unclassified)
                cat = hit.category if hit else "unclassified"
                results[r["id"]] = (cat, hit.base if hit else 5, None, {"rule_tag": hit.tag if hit else "",
                                    "factors": []}, "rules-fallback")
                continue
            cat = x["category"]
            # Trust strong rule categories over the model for primary results filings.
            if hit and hit.tag == "results_primary":
                cat = "results"
            mat, factors = score(cat, hit, x, ctx.get(r["symbol"], {}))
            one = x.get("one_liner") if mat >= ROUTINE_BELOW else None
            grounded = True
            if one and not numbers_grounded(one, f"{r['subject']} {r['note'] or ''}"):
                grounded = False
                one = r["note"] or None   # fall back to the filing's own text
            enrich = {"rule_tag": hit.tag if hit else "", "factors": factors, "one_liner_grounded": grounded,
                      "amount_cr": x.get("amount_cr"), "instrument": x.get("instrument"),
                      "rating_action": x.get("rating_action"), "people": x.get("people") or [],
                      "is_order_win": x.get("is_order_win")}
            results[r["id"]] = (cat, mat, one, enrich, llm.BULK)
            stats["llm"] += 1

    with cursor() as c:
        for fid, (cat, mat, one, enrich, by) in results.items():
            c.execute("update public.filings set category = %s, materiality = %s, one_liner = %s, "
                      "enrichment = coalesce(enrichment, '{}'::jsonb) || %s::jsonb, classified_by = %s "
                      "where id = %s", (cat, mat, one, json.dumps(enrich), by, fid))
    return stats


if __name__ == "__main__":
    print(classify_pending(reclassify_all="--all" in sys.argv))
