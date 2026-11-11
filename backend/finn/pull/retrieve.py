"""Hybrid retrieval over a company's uploaded documents.

Vector search (pgvector cosine on gemini-embedding-2 @768d) and Postgres
full-text search run independently, then merge with reciprocal rank fusion
(RRF): semantic recall + exact-term precision (numbers, product names).
Query embeddings are cached in llm_cache so repeated questions are free.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from finn import llm
from finn.db import cursor

RRF_K = 60


@dataclass
class Chunk:
    chunk_id: int
    document_id: int
    doc_label: str
    kind: str
    period: str
    page: int
    content: str
    score: float

    def ref(self) -> dict:
        return {"doc_id": self.document_id, "doc_label": self.doc_label, "page": self.page}


def embed_query(q: str) -> list[float]:
    key = "emb:" + hashlib.sha256(f"{llm.EMBED}|{llm.EMBED_DIM}|{q}".encode()).hexdigest()
    with cursor(commit=False) as c:
        c.execute("select response from public.llm_cache where key = %s", (key,))
        hit = c.fetchone()
    if hit:
        r = hit[0] if not isinstance(hit[0], str) else json.loads(hit[0])
        return r["v"]
    v = llm.embed([q], task_type="RETRIEVAL_QUERY")[0]
    with cursor() as c:
        c.execute("insert into public.llm_cache (key, model, response) values (%s, %s, %s::jsonb) "
                  "on conflict (key) do nothing", (key, llm.EMBED, json.dumps({"v": v})))
    return v


def search(symbol: str, query: str, *, k: int = 8, kind: str | None = None,
           document_ids: list[int] | None = None, pool: int = 30) -> list[Chunk]:
    vec = "[" + ",".join(f"{x:.6f}" for x in embed_query(query)) + "]"
    filt = " and (%s::text is null or d.kind = %s::text) and (%s::bigint[] is null or d.id = any(%s::bigint[]))"
    fargs = (kind, kind, document_ids, document_ids)
    with cursor(commit=False) as c:
        c.execute(
            f"""select ch.id from public.doc_chunks ch join public.documents d on d.id = ch.document_id
                where ch.symbol = %s {filt}
                order by ch.embedding <=> %s::extensions.vector limit %s::int""",
            (symbol, *fargs, vec, pool))
        vec_ids = [r[0] for r in c.fetchall()]
        c.execute(
            f"""select ch.id from public.doc_chunks ch join public.documents d on d.id = ch.document_id
                where ch.symbol = %s {filt}
                  and ch.tsv @@ websearch_to_tsquery('english', %s)
                order by ts_rank_cd(ch.tsv, websearch_to_tsquery('english', %s)) desc limit %s::int""",
            (symbol, *fargs, query, query, pool))
        fts_ids = [r[0] for r in c.fetchall()]
        scores: dict[int, float] = {}
        for rank, cid in enumerate(vec_ids):
            scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
        for rank, cid in enumerate(fts_ids):
            scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
        top = sorted(scores, key=lambda i: -scores[i])[:k]
        if not top:
            return []
        c.execute("""select ch.id, d.id, coalesce(d.label, d.kind), d.kind, d.period, ch.page, ch.content
                     from public.doc_chunks ch join public.documents d on d.id = ch.document_id
                     where ch.id = any(%s::bigint[])""", (top,))
        rows = {r[0]: r for r in c.fetchall()}
    return [Chunk(chunk_id=i, document_id=rows[i][1], doc_label=rows[i][2], kind=rows[i][3], period=str(rows[i][4]),
                  page=rows[i][5], content=rows[i][6], score=round(scores[i], 5)) for i in top if i in rows]


def documents(symbol: str) -> list[dict]:
    with cursor(commit=False) as c:
        c.execute("""select id, kind, period, label, filename, sha256, pages, pages_kept, chunks, ingested_at
                     from public.documents where symbol = %s order by period desc""", (symbol,))
        return [{"id": i, "kind": k, "period": str(p) if p else None, "label": lb, "filename": fn, "sha256": sha,
                 "pages": pg, "pages_kept": pk, "chunks": ch, "ingested_at": ts.isoformat()}
                for i, k, p, lb, fn, sha, pg, pk, ch, ts in c.fetchall()]
