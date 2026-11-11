"""Citations: number retrieved chunks for the prompt ([c1]...), and verify
that every quote a model returns really occurs in the chunk it cites."""
from __future__ import annotations

import re
import unicodedata

from finn.pull.retrieve import Chunk


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = re.sub(r"[^a-z0-9%₹.$ ]+", " ", s)      # drop most punctuation
    s = re.sub(r"(?<=\d)[ ,](?=\d{2,3}\b)", "", s)   # 1,000 / 1 000 -> 1000
    return re.sub(r"\s+", " ", s).strip()


def quote_in(quote: str, text: str) -> bool:
    q, t = _norm(quote), _norm(text)
    if len(q) < 12:
        return False
    if q in t:
        return True
    # PDF text layers often break spacing ("15 %", "crore s", "1 , 600"). Compare
    # with all spacing/punctuation removed: still exact on every letter and digit.
    if _squash(quote) in _squash(text):
        return True
    # tolerate an elided middle ("...") by requiring every long fragment to match
    parts = [p.strip() for p in re.split(r"\.\.\.|…", quote) if len(p.strip()) >= 12]
    return bool(parts) and all(_norm(p) in t or _squash(p) in _squash(text) for p in parts)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9%₹]", "", _norm(s))


def chunk_block(chunks: list[Chunk], prefix: str = "c") -> tuple[str, dict[str, Chunk]]:
    refs = {f"{prefix}{i + 1}": ch for i, ch in enumerate(chunks)}
    lines = [f"[{r}] ({ch.doc_label}, p.{ch.page})\n{ch.content}" for r, ch in refs.items()]
    return "\n\n".join(lines), refs


def citation(ref_id: str, ch: Chunk, quote: str) -> dict:
    return {"id": ref_id, "doc_id": ch.document_id, "doc_label": ch.doc_label, "page": ch.page, "quote": quote}


def number_citation(ref_id: str, fact: str) -> dict:
    return {"id": ref_id, "doc_id": None, "doc_label": "screener financials", "page": None, "quote": fact}
