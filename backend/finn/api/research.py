"""Research (pull) API + LLM usage stats for the cost meter.

Mount in finn/api/main.py:
    from finn.api.research import router as research_router, usage_router
    app.include_router(research_router)
    app.include_router(usage_router)
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from finn.api.auth import User, current_user
from finn.db import cursor
from finn.pull import sections as S
from finn.pull.ask import ask as ask_fn
from finn.pull.company import CompanyNotFound, company_meta, ensure_company, normalise
from finn.pull.docs import ingest_pdf
from finn.pull.retrieve import documents

router = APIRouter(prefix="/research", tags=["research"])
usage_router = APIRouter(tags=["usage"])

MAX_UPLOAD = 40 * 1024 * 1024


def _sym(symbol: str) -> str:
    try:
        return normalise(symbol)
    except CompanyNotFound as e:
        raise HTTPException(422, str(e))


def _require(symbol: str) -> dict:
    meta = company_meta(symbol)
    if not meta:
        raise HTTPException(404, f"{symbol} not loaded yet: call POST /research/{symbol}/ensure first")
    return meta


def _overview(symbol: str, meta: dict) -> dict:
    docs = documents(symbol)
    n_tr = sum(1 for d in docs if d["kind"] == "transcript")
    n_ar = sum(1 for d in docs if d["kind"] == "annual_report")
    return {**meta,
            "docs": {"transcripts": n_tr, "annual_reports": n_ar,
                     "items": [{k: d[k] for k in ("id", "kind", "period", "label", "pages", "pages_kept", "chunks")}
                               for d in docs]},
            "sections_available": {"snapshot": True, "health": True, "bull_bear": True,
                                   "promise_delivered": n_tr > 0}}


@router.post("/{symbol}/ensure")
def ensure(symbol: str, user: User = Depends(current_user)):
    sym = _sym(symbol)
    try:
        meta = ensure_company(sym)
    except CompanyNotFound as e:
        raise HTTPException(404, str(e))
    return _overview(sym, meta)


@router.get("/{symbol}")
def overview(symbol: str, user: User = Depends(current_user)):
    sym = _sym(symbol)
    return _overview(sym, _require(sym))


@router.get("/{symbol}/sections/{section}")
def section(symbol: str, section: str, refresh: bool = False, user: User = Depends(current_user)):
    sym = _sym(symbol)
    if section not in S.SECTIONS:
        raise HTTPException(404, f"Unknown section; use one of {S.SECTIONS}")
    _require(sym)
    return S.get_section(sym, section, force=refresh)


@router.post("/{symbol}/documents")
async def upload(symbol: str, file: UploadFile = File(...), kind: str = Form(...), period: str = Form(...),
                 user: User = Depends(current_user)):
    sym = _sym(symbol)
    _require(sym)
    if kind not in ("annual_report", "transcript"):
        raise HTTPException(422, "kind must be annual_report or transcript")
    try:
        p = date.fromisoformat(period)
    except ValueError:
        raise HTTPException(422, "period must be YYYY-MM-DD")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "PDF larger than 40 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "Not a PDF")
    try:
        res = ingest_pdf(sym, data, kind, p, file.filename or "", uploaded_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if res["status"] == "ingested":
        S.invalidate(sym)
    return res


class AskReq(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/{symbol}/ask")
def ask(symbol: str, req: AskReq, user: User = Depends(current_user)):
    sym = _sym(symbol)
    _require(sym)
    return ask_fn(sym, req.question)


@usage_router.get("/usage")
def usage(days: int = 7, user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select task, model, count(*) filter (where not cache_hit), count(*) filter (where cache_hit),
                            coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0), sum(cost_usd)
                     from public.llm_calls where created_at >= now() - make_interval(days => %s::int)
                     group by task, model order by 5 desc""", (days,))
        rows = c.fetchall()
    by_task = [{"task": t, "model": m, "calls": n, "cache_hits": h, "tokens_in": int(ti), "tokens_out": int(to),
                "cost_usd": float(cost) if cost is not None else None} for t, m, n, h, ti, to, cost in rows]
    calls = sum(x["calls"] for x in by_task)
    hits = sum(x["cache_hits"] for x in by_task)
    return {"days": days, "calls": calls, "cache_hits": hits,
            "cache_hit_rate": round(hits / (calls + hits) * 100, 1) if calls + hits else None,
            "tokens_in": sum(x["tokens_in"] for x in by_task), "tokens_out": sum(x["tokens_out"] for x in by_task),
            "cost_usd": None if any(x["cost_usd"] is None for x in by_task if x["calls"]) else
            round(sum(x["cost_usd"] or 0 for x in by_task), 4),
            "by_task": by_task}
