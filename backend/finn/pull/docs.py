"""Primary-document ingestion: PDF -> pages -> chunks -> embeddings.

- pypdf (pure Python) for text, page numbers preserved on every chunk.
- Transcripts are ingested in full.
- Annual reports run 200-400 pages; most is statutory boilerplate. We keep
  the research-relevant pages: the opening letters/overview (first 20 pages),
  the Management Discussion & Analysis block (from its heading, next 45
  pages), and any other page that mentions segments/outlook/strategy/risk,
  capped at AR_PAGE_CAP pages. This keeps embedding cost and retrieval noise
  down; the choice is recorded per document (pages vs pages_kept).
- sha256 dedupe: the same PDF is never ingested twice.

Usage: python -m finn.pull.docs          # ingest everything in backend/docs_inbox/
"""
from __future__ import annotations

import hashlib
import io
import re
import time
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from finn import llm
from finn.db import cursor
from finn.push.results import latest_quarter_before, quarter_label

INBOX = Path(__file__).resolve().parent.parent.parent / "docs_inbox"
AR_PAGE_CAP = 120
CHUNK_CHARS = 1200
OVERLAP = 150
EMBED_BATCH = 50

_AR_KEYWORDS = re.compile(
    r"management discussion|business overview|segment|outlook|strategy|strategic|key risks|risk management|"
    r"operating performance|financial performance|revenue mix|capital expenditure|capex|guidance|"
    r"chairman'?s (message|letter)|md'?s (message|letter)|ceo'?s (message|letter)|key highlights|"
    r"performance highlights|order book|market share|capacity", re.I)


DOC_KINDS = ("annual_report", "transcript", "presentation")


def doc_label(kind: str, period: date) -> str:
    if kind == "transcript":
        return f"{quarter_label(_col(latest_quarter_before(period)))} concall"
    if kind == "annual_report":
        return f"Annual Report FY{str(period.year)[-2:]}"
    if kind == "presentation":
        return f"Investor presentation {period:%b %Y}"
    return f"{kind.replace('_', ' ').title()} {period:%b %Y}"


def _col(d: date) -> str:
    return d.strftime("%b %Y")


def _clean(t: str) -> str:
    t = t.replace("\x00", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_pages(data: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(data))
    out = []
    for p in reader.pages:
        try:
            out.append(_clean(p.extract_text() or ""))
        except Exception:
            out.append("")
    return out


def select_ar_pages(pages: list[str]) -> list[int]:
    """Indices of annual-report pages worth keeping (see module docstring)."""
    n = len(pages)
    if n <= AR_PAGE_CAP:
        return [i for i in range(n) if pages[i]]
    keep: set[int] = set(range(min(20, n)))
    mdna = next((i for i, t in enumerate(pages) if re.search(r"management discussion\s*(and|&)\s*analysis", t, re.I)
                 and i > 5), None)
    if mdna is not None:
        keep.update(range(mdna, min(mdna + 45, n)))
    for i, t in enumerate(pages):
        if len(keep) >= AR_PAGE_CAP:
            break
        if _AR_KEYWORDS.search(t):
            keep.add(i)
    return sorted(i for i in keep if pages[i])[:AR_PAGE_CAP]


def chunk_page(text: str, page_no: int) -> list[tuple[int, str]]:
    """Split one page into ~CHUNK_CHARS chunks on paragraph/sentence boundaries."""
    if len(text) <= CHUNK_CHARS:
        return [(page_no, text)] if len(text) > 40 else []
    pieces = re.split(r"(?<=[.!?])\s+|\n\n", text)
    chunks, buf = [], ""
    for p in pieces:
        if len(buf) + len(p) + 1 > CHUNK_CHARS and buf:
            chunks.append(buf.strip())
            buf = buf[-OVERLAP:] + " " + p
        else:
            buf = f"{buf} {p}" if buf else p
    if len(buf.strip()) > 40:
        chunks.append(buf.strip())
    return [(page_no, c) for c in chunks]


_RETRY_IN = re.compile(r"retry(?:Delay'?:?\s*'?| in )(\d+(?:\.\d+)?)s", re.I)


def _rate_limit_wait(err: Exception, attempt: int) -> float:
    """Free-tier quotas are per minute. Honour the delay Google returns when
    it gives one; otherwise back off 15s, 30s, then a full minute."""
    msg = str(err)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        m = _RETRY_IN.search(msg)
        return float(m.group(1)) + 2 if m else min(15 * (2 ** attempt), 65)
    return 4 * (attempt + 1)


def _embed_all(texts: list[str]) -> list[list[float]]:
    vecs: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        for attempt in range(8):
            try:
                vecs.extend(llm.embed(batch, task_type="RETRIEVAL_DOCUMENT"))
                break
            except Exception as e:
                if attempt == 7:
                    raise
                time.sleep(_rate_limit_wait(e, attempt))
        time.sleep(0.4)   # pace batches so a large annual report doesn't burn a minute's quota at once
    return vecs


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def ingest_pdf(symbol: str, data: bytes, kind: str, period: date, filename: str = "",
               uploaded_by: str | None = None, progress=None, source: str | None = None,
               source_url: str | None = None) -> dict:
    """progress(stage, info) is called as work advances: 'reading', 'indexing'."""
    if kind not in DOC_KINDS:
        raise ValueError("kind must be one of " + ", ".join(DOC_KINDS))
    sha = hashlib.sha256(data).hexdigest()
    with cursor(commit=False) as c:
        c.execute("select id, chunks from public.documents where sha256 = %s", (sha,))
        hit = c.fetchone()
    if hit:
        return {"status": "duplicate", "document_id": hit[0], "chunks": hit[1]}

    t0 = time.time()
    if progress:
        progress("reading", {})
    pages = extract_pages(data)
    keep = select_ar_pages(pages) if kind == "annual_report" else [i for i in range(len(pages)) if pages[i]]
    if not keep:
        raise ValueError("No extractable text in PDF (scanned image?)")
    chunks: list[tuple[int, str]] = []
    for i in keep:
        chunks.extend(chunk_page(pages[i], i + 1))
    if progress:
        progress("indexing", {"pages": len(pages), "pages_kept": len(keep), "chunks": len(chunks)})
    vectors = _embed_all([c for _, c in chunks])
    label = doc_label(kind, period)

    with cursor() as c:
        c.execute("""insert into public.documents (symbol, kind, period, label, filename, sha256, pages, pages_kept,
                                                  chunks, uploaded_by, source, source_url)
                     values (%s, %s, %s::date, %s, %s, %s, %s::int, %s::int, %s::int, %s::uuid, %s, %s) returning id""",
                  (symbol, kind, period.isoformat(), label, filename, sha, len(pages), len(keep), len(chunks),
                   uploaded_by, source, source_url))
        doc_id = c.fetchone()[0]
        c.execute(
            """insert into public.doc_chunks (document_id, symbol, page, chunk_index, content, embedding)
               select %s::bigint, %s, p, i, t, e::extensions.vector
               from unnest(%s::int[], %s::int[], %s::text[], %s::text[]) as x(p, i, t, e)""",
            (doc_id, symbol, [p for p, _ in chunks], list(range(len(chunks))), [t for _, t in chunks],
             [_vec_literal(v) for v in vectors]),
        )
    return {"status": "ingested", "document_id": doc_id, "label": label, "pages": len(pages),
            "pages_kept": len(keep), "chunks": len(chunks), "seconds": round(time.time() - t0, 1)}


_NAME = re.compile(r"^(AR)-(\d{4})\.pdf$|^(CC)-(\d{4})-(\d{1,2})\.pdf$", re.I)


def parse_inbox_name(name: str) -> tuple[str, date] | None:
    m = _NAME.match(name)
    if not m:
        return None
    if m.group(1):
        return "annual_report", date(int(m.group(2)), 3, 31)
    y, mo = int(m.group(4)), int(m.group(5))
    return "transcript", date(y, mo, 1)


def ingest_inbox(root: Path = INBOX) -> list[dict]:
    from finn.pull.company import ensure_company
    out = []
    if not root.exists():
        return out
    for sym_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        pdfs = sorted(sym_dir.glob("*.pdf"))
        if not pdfs:
            continue
        ensure_company(sym_dir.name.upper())
        for f in pdfs:
            parsed = parse_inbox_name(f.name)
            if not parsed:
                out.append({"file": str(f), "status": "skipped: name must be AR-YYYY.pdf or CC-YYYY-MM.pdf"})
                continue
            kind, period = parsed
            try:
                r = ingest_pdf(sym_dir.name.upper(), f.read_bytes(), kind, period, f.name)
            except Exception as e:
                r = {"status": f"error: {type(e).__name__}: {str(e)[:150]}"}
            out.append({"file": f"{sym_dir.name}/{f.name}", **r})
    return out


if __name__ == "__main__":
    for r in ingest_inbox():
        print(r)
