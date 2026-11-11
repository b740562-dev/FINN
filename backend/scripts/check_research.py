"""Research (pull) pipeline check, run directly against the functions.

1. Demo symbol (INFY) and an unseen ticker (default TCS): ensure -> snapshot ->
   health -> bull_bear (numbers-only) -> promise_delivered (expects needs_docs).
2. Document pipeline on a locally generated PDF (no downloads): two fake
   'transcripts' with guidance are ingested under a throwaway company ZZTEST
   (financials copied from INFY), then retrieval, citation verification,
   promise-vs-delivered, bull/bear with docs and Q&A run end to end.
   All ZZTEST rows are deleted afterwards.

Usage: python scripts/check_research.py [UNSEEN_SYMBOL]
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.db import cursor  # noqa: E402
from finn.pull import sections as S  # noqa: E402
from finn.pull.ask import ask  # noqa: E402
from finn.pull.company import ensure_company  # noqa: E402
from finn.pull.docs import ingest_pdf  # noqa: E402
from finn.pull.retrieve import search  # noqa: E402


def make_pdf(pages: list[list[str]]) -> bytes:
    """Minimal text PDF (Helvetica), pure Python, extractable by pypdf."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        esc = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in lines]
        stream = "BT /F1 10 Tf 50 780 Td 14 TL " + " ".join(f"({ln}) '" for ln in esc) + " ET"
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        content_no = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {content_no} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


T1 = [  # call held May 2026 (Q4 FY26)
    ["ZZ Test Systems - Q4 FY26 Earnings Conference Call - transcript", "",
     "Moderator: Good evening and welcome to the earnings call.",
     "CEO: We closed FY26 with revenue of about 1,78,650 crore, growth of roughly 10 percent.",
     "CEO: For FY27 we expect revenue growth of 8 to 10 percent in constant currency.",
     "CFO: We expect our operating margin to remain in the 23 to 25 percent band for FY27.",
     "CFO: Capital expenditure for FY27 is planned at about 6,000 crore, mainly for new campuses.",
     "CEO: For Q1 FY27 we expect revenue to grow at least 15 percent year on year.",
     "CFO: We expect Q1 FY27 net profit to be above 7,500 crore."],
    ["Analyst: What are the key risks you see?",
     "CEO: Client spending in financial services remains cautious and pricing pressure is a headwind.",
     "CEO: Large deal wins and our AI services pipeline are the main growth drivers this year.",
     "Analyst: Will margins be under pressure from wage hikes?",
     "CFO: Wage hikes will weigh on margins in Q1, but we expect to recover through utilisation."],
]
T2 = [  # call held Oct 2026 (Q2 FY27)
    ["ZZ Test Systems - Q2 FY27 Earnings Conference Call - transcript", "",
     "CEO: Revenue grew 11 percent year on year this quarter, ahead of our plan.",
     "CEO: We now expect FY27 revenue growth of 10 to 12 percent, raising the earlier guidance.",
     "CFO: We expect Q3 FY27 operating margin of around 25 percent.",
     "CFO: We target net profit growth in double digits for FY27."],
]


def show(env: dict, dt: float) -> None:
    c = env["content"]
    tag = f"{env['section']:18} {env['status']:10} {dt:5.1f}s cached={env.get('cached')} model={env['model']}"
    if env["section"] == "bull_bear" and env["status"] == "ready":
        print(tag, "|", c["basis"], c["verification"])
        for side in ("bull", "bear"):
            for p in c[side]:
                print(f"     {side}: {p['point']} {p['citation_ids']}")
    elif env["section"] == "promise_delivered" and env["status"] == "ready":
        print(tag, "| score", c["score"], c.get("verification"))
        for it in c["items"]:
            print(f"     [{it['verdict']:12}] {it['said_in']}: {it['promise']} | target {it['target']} | actual "
                  f"{it['actual']} -> {it['explanation']}")
    elif env["section"] == "snapshot":
        b = c.get("business")
        print(tag, "| ttm", c["financial"]["ttm"], "| business:", (b or {}).get("summary"),
              [s["name"] for s in (b or {}).get("segments", [])], c.get("verification"))
    else:
        print(tag, "|", c.get("reason") or c.get("error") or "")


def run_symbol(sym: str) -> None:
    t = time.time()
    meta = ensure_company(sym)
    print(f"\n== {sym}: ensure {time.time() - t:.1f}s created={meta['created']} name={meta['name']}")
    for sec in ("snapshot", "health", "bull_bear", "promise_delivered"):
        t = time.time()
        env = S.get_section(sym, sec)
        show(env, time.time() - t)
    t = time.time()
    env = S.get_section(sym, "bull_bear")
    print(f"   bull_bear again: cached={env.get('cached')} {time.time() - t:.2f}s")


def run_docs() -> None:
    sym = "ZZTEST"
    with cursor() as c:
        c.execute("delete from public.companies where symbol = %s", (sym,))
        c.execute("insert into public.companies (symbol, name, sector, basis, market_cap_cr) "
                  "select %s, 'ZZ Test Systems', 'IT services', basis, market_cap_cr from public.companies "
                  "where symbol = 'INFY'", (sym,))
        c.execute("insert into public.fundamentals (symbol, basis, tables) select %s, basis, tables "
                  "from public.fundamentals where symbol = 'INFY'", (sym,))
    try:
        print("\n== document pipeline (throwaway ZZTEST, INFY's numbers)")
        for pages, period in ((T1, date(2026, 5, 1)), (T2, date(2026, 10, 1))):
            t = time.time()
            r = ingest_pdf(sym, make_pdf(pages), "transcript", period, "generated.pdf")
            print(f"   ingest {r.get('label')}: {r['status']} pages={r.get('pages')} chunks={r.get('chunks')} "
                  f"({time.time() - t:.1f}s)")
        again = ingest_pdf(sym, make_pdf(T1), "transcript", date(2026, 5, 1))
        print("   re-ingest same PDF ->", again["status"])
        hits = search(sym, "margin guidance band", k=3)
        print("   retrieval 'margin guidance band' ->", [(h.doc_label, h.page, h.content[:60]) for h in hits])
        for sec in ("snapshot", "promise_delivered", "bull_bear"):
            t = time.time()
            show(S.get_section(sym, sec), time.time() - t)
        t = time.time()
        a = ask(sym, "What did management say about margins for FY27?")
        print(f"   ask ({time.time() - t:.1f}s): {a['answer']}\n     citations:",
              [(c['id'], c['doc_label'], c['page']) for c in a["citations"]], a["verification"])
        a = ask(sym, "What is the company's dividend policy?")
        print(f"   ask (not in docs): found={a['found']} -> {a['answer'][:140]}")
    finally:
        with cursor() as c:
            c.execute("delete from public.llm_calls where ref_id like 'ZZTEST%%' or ref_id like '%%:ZZTEST%%'")
            c.execute("delete from public.companies where symbol = %s", (sym,))   # cascades docs/chunks/sections
            c.execute("select count(*) from public.documents where symbol = %s", (sym,))
            print("   cleanup: remaining ZZTEST documents =", c.fetchone()[0])


if __name__ == "__main__":
    t0 = time.time()
    if "--docs-only" not in sys.argv:
        run_symbol("INFY")
        run_symbol(next((a for a in sys.argv[1:] if not a.startswith("--")), "TCS"))
    run_docs()
    with cursor(commit=False) as c:
        c.execute("""select task, model, count(*) filter (where not cache_hit), sum(tokens_in), sum(tokens_out)
                     from public.llm_calls where created_at >= now() - interval '1 hour'
                       and task in ('research_business','promise_extract','promise_verdict','bull_bear','ask')
                     group by task, model order by 1""")
        print("\nLLM usage (last hour, research tasks):")
        for r in c.fetchall():
            print("  ", r)
    print(f"total {time.time() - t0:.0f}s")
