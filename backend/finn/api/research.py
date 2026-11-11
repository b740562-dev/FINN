"""Research (pull) API + LLM usage stats for the cost meter.

Mount in finn/api/main.py:
    from finn.api.research import router as research_router, usage_router
    app.include_router(research_router)
    app.include_router(usage_router)
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
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


STALE_JOB_MIN = 20   # a job not updated for this long was interrupted (e.g. server restart)


def _job_update(job_id: int, status: str, result: dict | None = None, error: str | None = None) -> None:
    with cursor() as c:
        c.execute("""update public.ingest_jobs set status = %s,
                       result = coalesce(%s::jsonb, result), error = %s, updated_at = now()
                     where id = %s""",
                  (status, json.dumps(result) if result is not None else None, error, job_id))


def _run_ingest(job_id: int, sym: str, data: bytes, kind: str, period: date, filename: str, user_id: str) -> None:
    """Background worker: read -> index -> rebuild the document-based sections."""
    try:
        res = ingest_pdf(sym, data, kind, period, filename, uploaded_by=user_id,
                         progress=lambda stage, info: _job_update(job_id, stage, info or None))
        if res["status"] == "duplicate":
            _job_update(job_id, "duplicate", res)
            return
        S.invalidate(sym)
        _job_update(job_id, "analysing", res)
        # Rebuild what the new document unlocks, so it's ready when the user looks.
        for sec in ("snapshot", "promise_delivered", "bull_bear"):
            try:
                S.get_section(sym, sec)
            except Exception:
                pass  # the section is rebuilt on demand if this fails
        _job_update(job_id, "done", res)
    except ValueError as e:
        _job_update(job_id, "failed", error=str(e))
    except Exception as e:  # never leave a job spinning
        _job_update(job_id, "failed", error=f"{type(e).__name__}: {str(e)[:200]}")


@router.post("/{symbol}/documents", status_code=202)
async def upload(symbol: str, background: BackgroundTasks, file: UploadFile = File(...), kind: str = Form(...),
                 period: str = Form(...), user: User = Depends(current_user)):
    """Accepts a PDF and processes it in the background. Documents are shared by
    every user, so guests can't add them (one bad upload would change everyone's
    research); the demo set is pre-loaded."""
    if user.is_anonymous:
        raise HTTPException(403, "Guests can read every pre-loaded document. To add documents, save your account "
                                 "with an email (You → Account).")
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

    sha = hashlib.sha256(data).hexdigest()
    with cursor() as c:
        c.execute("select id, label from public.documents where sha256 = %s", (sha,))
        dup = c.fetchone()
        if dup:  # instant answer, no job needed
            return {"status": "duplicate", "document_id": dup[0], "label": dup[1]}
        c.execute("""insert into public.ingest_jobs (symbol, filename, kind, period, created_by)
                     values (%s, %s, %s, %s::date, %s::uuid) returning id""",
                  (sym, file.filename or "", kind, p.isoformat(), user.id))
        job_id = c.fetchone()[0]
    background.add_task(_run_ingest, job_id, sym, data, kind, p, file.filename or "", user.id)
    return {"status": "queued", "job_id": job_id}


@router.get("/{symbol}/jobs/{job_id}")
def job(symbol: str, job_id: int, user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select id, status, result, error, filename, kind, period, created_at, updated_at,
                            (updated_at < now() - make_interval(mins => %s::int)) as stale
                     from public.ingest_jobs where id = %s and symbol = %s""",
                  (STALE_JOB_MIN, job_id, _sym(symbol)))
        r = c.fetchone()
    if not r:
        raise HTTPException(404, "No such job")
    jid, status, result, error, fname, kind, period, created, updated, stale = r
    if stale and status not in ("done", "duplicate", "failed"):
        status, error = "failed", "Interrupted (the server restarted). Please upload again."
    if isinstance(result, str):
        result = json.loads(result)
    return {"id": jid, "status": status, "result": result, "error": error, "filename": fname, "kind": kind,
            "period": str(period), "seconds": round((updated - created).total_seconds(), 1)}


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
