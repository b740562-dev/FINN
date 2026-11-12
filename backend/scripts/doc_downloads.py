"""Make fetching primary documents a few minutes of clicking.

BSE serves filings only to real browsers, so a person downloads them; this
script does everything else.

  python scripts/doc_downloads.py list [SYMBOL ...]
      Writes docs_inbox/download-list.html: one link per document (last 4
      concall transcripts + latest annual report per company), plus
      docs_inbox/download-map.json mapping each file's BSE id to
      (symbol, inbox filename).

  python scripts/doc_downloads.py missing [--from DIR]
      Writes docs_inbox/download-list-missing.html for documents not yet in
      Downloads: three BSE link variants each, plus company fallbacks.

  python scripts/doc_downloads.py sort [--from DIR] [--no-ingest]
      Finds those files in your Downloads folder by their BSE id (no renaming
      needed), copies them into docs_inbox/<SYMBOL>/ as AR-YYYY.pdf /
      CC-YYYY-MM.pdf, ingests them and rebuilds the research sections.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn.sources.screener import fetch_company  # noqa: E402

INBOX = Path(__file__).resolve().parent.parent / "docs_inbox"
MAP = INBOX / "download-map.json"
PAGE = INBOX / "download-list.html"
DEFAULT = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"]
_ID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def build_list(symbols: list[str]) -> None:
    INBOX.mkdir(exist_ok=True)
    entries = []
    for sym in symbols:
        p = fetch_company(sym)
        calls = [c for c in p.concalls if c.transcript_url][:4]
        for c in calls:
            mon, yr = c.period.split()
            entries.append({"symbol": sym, "name": p.name, "kind": "transcript", "label": f"{c.period} concall transcript",
                            "url": c.transcript_url, "target": f"CC-{yr}-{_MON[mon]:02d}.pdf", "optional": False})
        if p.annual_reports:
            a = p.annual_reports[0]
            entries.append({"symbol": sym, "name": p.name, "kind": "annual_report", "label": f"{a.label} (large, optional)",
                            "url": a.url, "target": f"AR-{a.year}.pdf", "optional": True})
    for e in entries:
        m = _ID.search(e["url"])
        e["id"] = m.group(1).lower() if m else None
    MAP.write_text(json.dumps(entries, indent=1), encoding="utf-8")

    rows, cur = [], None
    for i, e in enumerate(entries, 1):
        if e["symbol"] != cur:
            cur = e["symbol"]
            rows.append(f'<tr class="co"><td colspan="3">{html.escape(e["symbol"])} · {html.escape(e["name"])}</td></tr>')
        rows.append(
            f'<tr class="{"opt" if e["optional"] else ""}"><td><input type="checkbox" id="c{i}"></td>'
            f'<td><label for="c{i}">{html.escape(e["label"])}</label></td>'
            f'<td><a href="{html.escape(e["url"])}" target="_blank" rel="noreferrer" '
            f'onclick="document.getElementById(\'c{i}\').checked=true">open ↗</a></td></tr>')
    n_req = sum(not e["optional"] for e in entries)
    PAGE.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FINN document list</title>
<style>
 body{{background:#0a0c0f;color:#e6e8eb;font:14px/1.5 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:24px 16px}}
 h1{{font:700 20px ui-monospace,monospace;letter-spacing:.08em}} h1 b{{color:#f0b43c}}
 ol{{color:#cfd3d9;padding-left:20px}} li{{margin:4px 0}} code{{color:#f0b43c}}
 table{{width:100%;border-collapse:collapse;margin-top:16px}} td{{padding:8px 6px;border-top:1px solid #1d2128}}
 tr.co td{{font:700 12px ui-monospace,monospace;color:#f0b43c;letter-spacing:.08em;padding-top:18px;border-top:0}}
 tr.opt td{{color:#9aa1ad}} a{{color:#f0b43c;font:12px ui-monospace,monospace}}
 input{{accent-color:#f0b43c;width:16px;height:16px}} input:checked+label,tr:has(input:checked) label{{color:#6b7280;text-decoration:line-through}}
 .note{{color:#9aa1ad;font-size:12.5px;margin-top:18px}}
</style></head><body>
<h1>FINN<b>.</b> documents to fetch</h1>
<ol>
 <li>Click <b>open ↗</b> for each row. The PDF opens from BSE in your browser.</li>
 <li>Save it (download icon or <code>Ctrl+S</code>) into your normal <b>Downloads</b> folder. <b>Don't rename it.</b></li>
 <li>When done, tell Claude <b>"downloads done"</b>. It finds the files by their BSE id, files them, reads them and rebuilds the research.</li>
</ol>
<p class="note">{n_req} transcripts are what power Promise vs Delivered. Annual reports are large (10–40 MB) and optional:
they add the business-mix summary. Links come from screener.in; files are the companies' own exchange filings.</p>
<table>{''.join(rows)}</table>
</body></html>""", encoding="utf-8")
    print(f"wrote {PAGE} ({len(entries)} documents, {n_req} required) and {MAP.name}")
    for e in entries:
        print(f"  {e['symbol']:10} {e['target']:16} id={e['id']}  {'(optional)' if e['optional'] else ''}")


BSE = "https://www.bseindia.com"


def _alternates(doc_id: str) -> list[tuple[str, str]]:
    """BSE serves the same filing under three paths; when one fails in the
    browser another usually works. The id (and so the saved filename) is the
    same for all three, so the sorter recognises whichever one is used."""
    return [("link A", f"{BSE}/xml-data/corpfiling/AttachLive/{doc_id}.pdf"),
            ("link B", f"{BSE}/xml-data/corpfiling/AttachHis/{doc_id}.pdf"),
            ("link C", f"{BSE}/stockinfo/AnnPdfOpen.aspx?Pname={doc_id}.pdf")]


def _found_ids(src: Path) -> set[str]:
    got = set()
    for f in src.glob("*.pdf"):
        m = _ID.search(f.name)
        if m and f.read_bytes()[:5] == b"%PDF-":
            got.add(m.group(1).lower())
    return got


def build_missing_list(src: Path) -> None:
    """Re-issue the list for documents not yet in Downloads, with every link
    variant plus the company's BSE announcements and screener pages."""
    entries = json.loads(MAP.read_text(encoding="utf-8"))
    have = _found_ids(src)
    missing = [e for e in entries if e["id"] not in have]
    codes = {}
    for sym in {e["symbol"] for e in missing}:
        codes[sym] = fetch_company(sym).bse_code
    rows, cur = [], None
    for i, e in enumerate(missing, 1):
        if e["symbol"] != cur:
            cur = e["symbol"]
            code = codes.get(cur)
            rows.append(
                f'<tr class="co"><td colspan="3">{html.escape(cur)} · {html.escape(e["name"])} '
                f'<span class="fb">fallback: <a href="https://www.screener.in/company/{cur}/consolidated/#documents" '
                f'target="_blank" rel="noreferrer">screener documents</a>'
                + (f' · <a href="{BSE}/stock-share-price/x/{cur}/{code}/corp-announcements/" target="_blank" '
                   f'rel="noreferrer">BSE announcements</a>' if code else "") + "</span></td></tr>")
        links = " ".join(f'<a href="{html.escape(u)}" target="_blank" rel="noreferrer" '
                         f'onclick="document.getElementById(\'m{i}\').checked=true">{lbl}</a>'
                         for lbl, u in _alternates(e["id"]))
        rows.append(f'<tr class="{"opt" if e["optional"] else ""}"><td><input type="checkbox" id="m{i}"></td>'
                    f'<td><label for="m{i}">{html.escape(e["label"])}<br><span class="id">file id {e["id"][:8]}…</span>'
                    f'</label></td><td class="links">{links}</td></tr>')
    out = INBOX / "download-list-missing.html"
    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FINN missing documents</title>
<style>
 body{{background:#0a0c0f;color:#e6e8eb;font:14px/1.5 system-ui,sans-serif;max-width:760px;margin:0 auto;padding:24px 16px}}
 h1{{font:700 20px ui-monospace,monospace;letter-spacing:.08em}} h1 b{{color:#f0b43c}}
 ol{{color:#cfd3d9;padding-left:20px}} li{{margin:4px 0}}
 table{{width:100%;border-collapse:collapse;margin-top:16px}} td{{padding:8px 6px;border-top:1px solid #1d2128;vertical-align:top}}
 tr.co td{{font:700 12px ui-monospace,monospace;color:#f0b43c;letter-spacing:.06em;padding-top:18px;border-top:0}}
 .fb{{font-weight:400;color:#9aa1ad;margin-left:8px}} .fb a{{font-size:11px}}
 tr.opt td{{color:#9aa1ad}} a{{color:#f0b43c;font:12px ui-monospace,monospace;margin-right:10px;white-space:nowrap}}
 .id{{font:11px ui-monospace,monospace;color:#6b7280}} input{{accent-color:#f0b43c;width:16px;height:16px}}
 tr:has(input:checked) label{{color:#6b7280;text-decoration:line-through}}
</style></head><body>
<h1>FINN<b>.</b> still missing ({len(missing)})</h1>
<ol>
 <li>For each row try <b>link A</b>. If it shows an error, try <b>link B</b>, then <b>link C</b>.</li>
 <li>Save the PDF into <b>Downloads</b>; don't rename it. Any of the three gives the same file.</li>
 <li>If all three fail, use the company's <b>fallback</b> links and download the transcript for that month.
     Then save it as e.g. <code>TITAN_CC-2026-02.pdf</code> so it can still be filed.</li>
</ol>
<table>{''.join(rows)}</table></body></html>""", encoding="utf-8")
    print(f"wrote {out} with {len(missing)} missing documents")
    for e in missing:
        print(f"  {e['symbol']:10} {e['target']}")


def sort_downloads(src: Path, ingest: bool) -> None:
    entries = json.loads(MAP.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in entries if e["id"]}
    found, placed = set(), []
    by_name = {f"{e['symbol']}_{e['target']}".lower(): e for e in entries}   # fallback naming
    for f in sorted(src.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True):
        m = _ID.search(f.name)
        e = by_id.get(m.group(1).lower()) if m else by_name.get(f.name.lower())
        if not e or e["id"] in found:
            continue
        head = f.read_bytes()[:5]
        if head != b"%PDF-":
            print(f"  skip {f.name}: not a PDF (an error page saved instead?)")
            continue
        dest = INBOX / e["symbol"] / e["target"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        found.add(e["id"])
        placed.append(e)
        print(f"  {f.name[:40]:40} -> {e['symbol']}/{e['target']}  ({f.stat().st_size / 1e6:.1f} MB)")
    missing = [e for e in entries if e["id"] not in found]
    print(f"\nplaced {len(placed)} of {len(entries)} "
          f"({sum(not e['optional'] for e in placed)}/{sum(not e['optional'] for e in entries)} required transcripts)")
    for e in missing:
        print(f"  missing: {e['symbol']} {e['label']}")
    if not (ingest and placed):
        return

    from finn.pull import sections as S
    from finn.pull.docs import ingest_inbox
    from finn.pull.prewarm import prewarm
    print("\ningesting…")
    for r in ingest_inbox():
        print(f"  {r.get('file')}: {r.get('status')} pages={r.get('pages_kept', r.get('pages'))} chunks={r.get('chunks')}"
              f" {r.get('seconds', '')}s")
    from scripts.backfill_doc_sources import backfill
    print("linked to BSE source:", backfill())
    syms = sorted({e["symbol"] for e in placed})
    for s in syms:
        S.invalidate(s)
    print("\nrebuilding research…")
    for r in prewarm(syms):
        print(f"  {r['symbol']:10} promise_delivered={r['promise_delivered']}  bull_bear={r['bull_bear']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        build_list([a.upper() for a in args[1:]] or DEFAULT)
    elif args[0] == "missing":
        build_missing_list(Path(args[args.index("--from") + 1]) if "--from" in args else Path.home() / "Downloads")
    elif args[0] == "sort":
        src = Path(args[args.index("--from") + 1]) if "--from" in args else Path.home() / "Downloads"
        sort_downloads(src, ingest="--no-ingest" not in args)
    else:
        print(__doc__)
