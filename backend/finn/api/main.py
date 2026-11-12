"""FINN API.

Run locally:  uvicorn finn.api.main:app --reload --port 8000   (from backend/)

All per-user queries filter on the verified user id. The backend talks to
Postgres directly (bypassing RLS), so the user_id filter here is the guard;
RLS still protects the tables from direct Data API access.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from finn.api.auth import User, current_user
from finn.db import cursor
from finn.push.alerts import run_alerts
from finn.push.classify import CATEGORIES
from finn.push.rank import build_digest

app = FastAPI(title="FINN API", version="0.1")

# Auth is a bearer token (no cookies), so CORS only decides which web origins
# may call us. Local dev on any localhost port is always allowed; production
# origins come from FRONTEND_ORIGINS (comma list) and FRONTEND_ORIGIN_REGEX
# (e.g. Vercel preview deployments: https://finn-.*\.vercel\.app).
_LOCAL = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
_extra = os.getenv("FRONTEND_ORIGIN_REGEX", "").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()],
    allow_origin_regex=f"({_LOCAL})|({_extra})" if _extra else _LOCAL,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Pull side: research dossier, document upload, Q&A; plus the cost meter.
from finn.api.research import docs_router, router as research_router, usage_router  # noqa: E402

app.include_router(research_router)
app.include_router(usage_router)
app.include_router(docs_router)

from finn.api.chat import router as chat_router  # noqa: E402

app.include_router(chat_router)


def _j(v):
    return v if not isinstance(v, str) else json.loads(v)


# ------------------------------------------------------------------ health
@app.get("/health")
def health():
    with cursor(commit=False) as c:
        c.execute("select max(date) from public.prices_eod")
        last = c.fetchone()[0]
    return {"ok": True, "prices_as_of": str(last) if last else None}


# -------------------------------------------------------------- portfolio
def _portfolio(uid: str) -> dict:
    with cursor(commit=False) as c:
        c.execute(
            """with last2 as (
                 select symbol, date, close,
                        row_number() over (partition by symbol order by date desc) rn
                 from public.prices_eod
                 where symbol in (select symbol from public.holdings where user_id = %s)
               )
               select h.symbol, co.name, co.sector, h.quantity, h.weight,
                      max(close) filter (where rn = 1), max(close) filter (where rn = 2),
                      max(date) filter (where rn = 1)
               from public.holdings h
               join public.companies co using (symbol)
               left join last2 l on l.symbol = h.symbol and l.rn <= 2
               where h.user_id = %s
               group by h.symbol, co.name, co.sector, h.quantity, h.weight""",
            (uid, uid),
        )
        rows = c.fetchall()
    items, total, day = [], 0.0, 0.0
    as_of = None
    for sym, name, sector, qty, w, close, prev, d in rows:
        qty = float(qty) if qty is not None else 0.0
        close = float(close) if close is not None else None
        prev = float(prev) if prev is not None else None
        value = qty * close if close else 0.0
        pnl = qty * (close - prev) if close and prev else 0.0
        total += value
        day += pnl
        as_of = max(as_of, d) if as_of and d else (d or as_of)
        items.append({"symbol": sym, "name": name, "sector": sector, "quantity": qty, "close": close,
                      "prev_close": prev, "change_pct": round((close / prev - 1) * 100, 2) if close and prev else None,
                      "value": round(value), "day_pnl": round(pnl), "target_weight": float(w) if w is not None else None})
    for it in items:
        it["weight"] = round(it["value"] / total * 100, 2) if total else (it["target_weight"] or 0)
    items.sort(key=lambda x: -x["value"])
    prev_total = total - day
    return {"holdings": items, "totals": {"value": round(total), "day_pnl": round(day),
            "day_pct": round(day / prev_total * 100, 2) if prev_total else None,
            "as_of": str(as_of) if as_of else None}}


def _rules(uid: str) -> dict:
    with cursor(commit=False) as c:
        c.execute("select volume_multiple, move_pct, categories, overrides from public.alert_rules where user_id = %s",
                  (uid,))
        r = c.fetchone()
    if not r:
        raise HTTPException(404, "No alert rules for user (account not seeded)")
    return {"volume_multiple": float(r[0]), "move_pct": float(r[1]), "categories": list(r[2] or []),
            "overrides": _j(r[3]) or {}}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": {"id": user.id, "is_anonymous": user.is_anonymous, "email": user.email, "is_admin": user.is_admin},
            **_portfolio(user.id), "rules": _rules(user.id)}


# ------------------------------------------------------------------ profile
PROFILE_FIELDS = ("full_name", "gender", "work_company", "work_role", "education", "city", "experience", "bio")


class ProfileIn(BaseModel):
    full_name: str | None = Field(None, max_length=80)
    gender: str | None = Field(None, pattern="^(female|male|non_binary|prefer_not_to_say)$")
    work_company: str | None = Field(None, max_length=80)
    work_role: str | None = Field(None, max_length=80)
    education: str | None = Field(None, max_length=120)
    city: str | None = Field(None, max_length=60)
    experience: str | None = Field(None, pattern="^(new|intermediate|experienced|professional)$")
    bio: str | None = Field(None, max_length=280)


def _profile(user: User) -> dict:
    with cursor(commit=False) as c:
        c.execute(f"select {', '.join(PROFILE_FIELDS)}, created_at, updated_at from public.profiles where user_id = %s",
                  (user.id,))
        r = c.fetchone()
    if not r:
        raise HTTPException(404, "Profile not found (account not seeded)")
    d = dict(zip(PROFILE_FIELDS + ("created_at", "updated_at"), r))
    d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
    d["updated_at"] = d["updated_at"].isoformat() if d["updated_at"] else None
    return {**d, "email": user.email, "is_anonymous": user.is_anonymous}


@app.get("/profile")
def get_profile(user: User = Depends(current_user)):
    return _profile(user)


@app.put("/profile")
def put_profile(req: ProfileIn, user: User = Depends(current_user)):
    vals = {k: (getattr(req, k) or "").strip() or None for k in PROFILE_FIELDS}
    with cursor() as c:
        c.execute(f"update public.profiles set {', '.join(f'{k} = %s' for k in PROFILE_FIELDS)}, updated_at = now() "
                  f"where user_id = %s", (*vals.values(), user.id))
    return _profile(user)


@app.get("/me/history")
def history(days: int = Query(90, ge=7, le=400), user: User = Depends(current_user)):
    """Portfolio value per trading day (current holdings x that day's close).
    Days where any holding lacks a price are skipped so the line never dips
    because of missing data rather than a real move."""
    with cursor(commit=False) as c:
        c.execute(
            """with h as (select symbol, quantity from public.holdings
                          where user_id = %s and quantity is not null and quantity > 0)
               select p.date, sum(h.quantity * p.close)
               from public.prices_eod p join h using (symbol)
               where p.date >= current_date - %s::int
               group by p.date
               having count(*) = (select count(*) from h)
               order by p.date""",
            (user.id, days),
        )
        rows = c.fetchall()
    pts = [{"date": str(d), "value": round(float(v))} for d, v in rows]
    first, last = (pts[0]["value"], pts[-1]["value"]) if pts else (None, None)
    return {"days": days, "points": pts,
            "change": (last - first) if pts else None,
            "change_pct": round((last / first - 1) * 100, 2) if pts and first else None}


@app.post("/bootstrap")
def bootstrap(user: User = Depends(current_user)):
    """Called by the app after sign-in: backfills the last 30 days of alerts so
    a brand-new account opens to a live inbox. Idempotent."""
    return run_alerts(lookback_days=30, user_id=user.id)


# ------------------------------------------------------------------ digest
WINDOWS = {"24h": 1, "7d": 7, "30d": 30}


@app.get("/digest")
def digest(window: str = Query("24h", pattern="^(24h|7d|30d|custom)$"),
           days: float | None = Query(None, gt=0, le=365),
           as_of: str | None = Query(None, description="YYYY-MM-DD: replay the digest as of this date"),
           user: User = Depends(current_user)):
    span = days if window == "custom" and days else WINDOWS.get(window, 1)
    until = datetime.now(timezone.utc)
    if as_of:
        try:
            until = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError:
            raise HTTPException(422, "as_of must be YYYY-MM-DD")
    pf = _portfolio(user.id)
    weights = {h["symbol"]: h["weight"] for h in pf["holdings"]}
    d = build_digest(weights, _rules(user.id)["categories"], since=until - timedelta(days=span), until=until)
    return {"window": window, "days": span, **d}


# ------------------------------------------------------------- company news
NEWS_REFRESH_HOURS = 6


@app.get("/news/{symbol}")
def company_news(symbol: str, days: int = Query(90, ge=1, le=365), user: User = Depends(current_user)):
    """Important filings for ANY listed company, held or not: "is there anything I
    should know before I buy this?". Loads the company on first search, refreshes
    its filings if they're stale, classifies anything new, then ranks it exactly
    like the digest (position size is 0 if you don't hold it)."""
    from finn.jobs.ingest import load_company
    from finn.pull.company import CompanyNotFound, ensure_company, normalise
    from finn.push.bios import enrich_management_changes
    from finn.push.classify import classify_pending
    from finn.push.results import attach_results_cards

    sym = normalise(symbol)
    try:
        meta = ensure_company(sym)
    except CompanyNotFound as e:
        raise HTTPException(404, str(e))
    fetched = meta.get("fundamentals_at")
    if not meta.get("created") and fetched and             datetime.fromisoformat(fetched) < datetime.now(timezone.utc) - timedelta(hours=NEWS_REFRESH_HOURS):
        try:
            load_company(sym)             # picks up filings posted since the last look
        except Exception:
            pass                          # stale beats nothing; the scheduler retries
    with cursor(commit=False) as c:
        c.execute("select count(*) from public.filings where symbol = %s and category is null", (sym,))
        pending = c.fetchone()[0]
    if pending:                           # same pipeline as the scheduler, cached per filing
        classify_pending()
        attach_results_cards()
        enrich_management_changes()

    weights = {h["symbol"]: h["weight"] for h in _portfolio(user.id)["holdings"]}
    d = build_digest({sym: weights.get(sym, 0.0)}, _rules(user.id)["categories"],
                     since=datetime.now(timezone.utc) - timedelta(days=days))
    return {"company": {"symbol": sym, "name": meta.get("name"), "sector": meta.get("sector"),
                        "market_cap_cr": meta.get("market_cap_cr")},
            "held": sym in weights, "days": days, **d}


# ------------------------------------------------------------------ alerts
@app.get("/alerts")
def alerts(limit: int = Query(50, le=200), user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select a.id, a.kind, a.symbol, co.name, a.filing_id, a.payload, a.event_date, a.created_at, a.read_at
                     from public.alerts a join public.companies co using (symbol)
                     where a.user_id = %s order by a.event_date desc nulls last, a.created_at desc limit %s""",
                  (user.id, limit))
        rows = c.fetchall()
        c.execute("select count(*) from public.alerts where user_id = %s and read_at is null", (user.id,))
        unread = c.fetchone()[0]
    return {"unread": unread, "items": [
        {"id": i, "kind": k, "symbol": s, "name": n, "filing_id": f, "payload": _j(p),
         "event_date": str(d) if d else None, "created_at": ca.isoformat(), "read": r is not None}
        for i, k, s, n, f, p, d, ca, r in rows]}


class ReadReq(BaseModel):
    ids: list[int] | None = None   # None = mark all read


@app.post("/alerts/read")
def mark_read(req: ReadReq, user: User = Depends(current_user)):
    with cursor() as c:
        if req.ids:
            c.execute("update public.alerts set read_at = now() where user_id = %s and id = any(%s::bigint[]) "
                      "and read_at is null", (user.id, req.ids))
        else:
            c.execute("update public.alerts set read_at = now() where user_id = %s and read_at is null", (user.id,))
        n = c.rowcount
    return {"marked": n}


# ------------------------------------------------------------------- rules
class RulesReq(BaseModel):
    volume_multiple: float = Field(ge=1.1, le=20)
    move_pct: float = Field(ge=0.5, le=50)
    categories: list[str]
    overrides: dict[str, dict[str, float]] = {}


@app.get("/rules")
def get_rules(user: User = Depends(current_user)):
    return {**_rules(user.id), "all_categories": CATEGORIES}


@app.put("/rules")
def put_rules(req: RulesReq, user: User = Depends(current_user)):
    bad = [c for c in req.categories if c not in CATEGORIES]
    if bad:
        raise HTTPException(422, f"Unknown categories: {bad}")
    with cursor() as c:
        c.execute("""update public.alert_rules set volume_multiple = %s, move_pct = %s, categories = %s::text[],
                     overrides = %s::jsonb where user_id = %s""",
                  (req.volume_multiple, req.move_pct, req.categories, json.dumps(req.overrides), user.id))
        # The user just redefined "unusual": rebuild the inbox under the new rules.
        c.execute("delete from public.alerts where user_id = %s and kind in ('move', 'volume', 'filing')", (user.id,))
    return {"rules": _rules(user.id), "alerts": run_alerts(lookback_days=30, user_id=user.id)}


# -------------------------------------------------------- holding signals
# Research colour-codes each holding. Every tag is computed from data, never
# generated: what's important (material filing lately), what's volatile (price
# swings), what looks promising (price trend backed by profit growth).
VOL_HIGH = 35.0        # annualised 20-day volatility, %. Absolute, not a 1-month move: a market-wide
                       # rally would otherwise tag every holding "volatile".
IMPORTANT_MAT = 60     # filing materiality
IMPORTANT_DAYS = 14


SIGNAL_RULES = {"important": f"filing with materiality ≥ {IMPORTANT_MAT} in the last {IMPORTANT_DAYS} days",
                "volatile": f"20-day price volatility ≥ {VOL_HIGH:g}% a year",
                "promising": "price up over 3 months and latest quarter's profit up > 10% YoY",
                "steady": "none of the above"}
_TAG_ORDER = {"important": 0, "volatile": 1, "promising": 2, "steady": 3}


def compute_signals(symbols: list[str]) -> dict[str, dict]:
    """Tags + the numbers behind them, for any companies FINN tracks."""
    import math

    from finn.push.results import build_card

    if not symbols:
        return {}
    with cursor(commit=False) as c:
        c.execute("""select symbol, array_agg(close order by date desc) from (
                       select symbol, date, close, row_number() over (partition by symbol order by date desc) rn
                       from public.prices_eod where symbol = any(%s::text[])) x
                     where rn <= 70 group by symbol""", (symbols,))
        closes = {s: [float(v) for v in arr if v is not None] for s, arr in c.fetchall()}
        c.execute("""select distinct on (symbol) symbol, materiality, category, coalesce(one_liner, subject), filed_at
                     from public.filings
                     where symbol = any(%s::text[]) and materiality >= %s
                       and filed_at >= now() - make_interval(days => %s::int)
                     order by symbol, materiality desc, filed_at desc""", (symbols, IMPORTANT_MAT, IMPORTANT_DAYS))
        news = {s: {"materiality": int(m), "category": cat, "headline": h, "filed_at": ts.isoformat()}
                for s, m, cat, h, ts in c.fetchall()}
        c.execute("select symbol, tables->'quarters', basis from public.fundamentals where symbol = any(%s::text[])",
                  (symbols,))
        quarters = {s: (q if isinstance(q, dict) else json.loads(q or "{}"), b) for s, q, b in c.fetchall()}

    def ret(px: list[float], n: int) -> float | None:
        return round((px[0] / px[n] - 1) * 100, 1) if len(px) > n and px[n] else None

    out = {}
    for s in symbols:
        px = closes.get(s, [])
        daily = [math.log(px[i] / px[i + 1]) for i in range(min(20, len(px) - 1)) if px[i] and px[i + 1]]
        vol = None
        if len(daily) >= 10:
            mu = sum(daily) / len(daily)
            vol = round(math.sqrt(sum((d - mu) ** 2 for d in daily) / (len(daily) - 1)) * math.sqrt(252) * 100, 1)
        r1m, r3m = ret(px, 21), ret(px, 63)
        pat_yoy, quarter = None, None
        if s in quarters:
            card = build_card(s, quarters[s][0], quarters[s][1])
            if card:
                quarter = card.get("quarter_label")
                pat = next((m for m in card.get("metrics", []) if m["key"] == "pat"), None)
                pat_yoy = pat.get("yoy_pct") if pat else None
        tags = []
        if s in news:
            tags.append("important")
        if vol is not None and vol >= VOL_HIGH:
            tags.append("volatile")
        if r3m is not None and r3m > 5 and pat_yoy is not None and pat_yoy > 10:
            tags.append("promising")
        if not tags:
            tags.append("steady")
        out[s] = {"symbol": s, "tags": tags, "primary": tags[0], "vol_20d": vol, "ret_1m": r1m, "ret_3m": r3m,
                  "pat_yoy": pat_yoy, "quarter": quarter, "news": news.get(s)}
    return out


def _counts(items: list[dict]) -> dict[str, int]:
    counts = {k: 0 for k in _TAG_ORDER}
    for x in items:
        for t in x["tags"]:
            counts[t] += 1
    return counts


@app.get("/holdings/signals")
def holding_signals(user: User = Depends(current_user)):
    pf = _portfolio(user.id)
    sig = compute_signals([h["symbol"] for h in pf["holdings"]])
    items = [{**sig[h["symbol"]], "name": h["name"], "weight": h["weight"]} for h in pf["holdings"]]
    items.sort(key=lambda x: (_TAG_ORDER[x["primary"]], -(x["weight"] or 0)))
    return {"items": items, "counts": _counts(items), "rules": SIGNAL_RULES}


@app.get("/signals")
def signals(symbols: str = Query(..., max_length=2000), user: User = Depends(current_user)):
    """Same tags for any tracked companies (Research → Other tracked)."""
    syms = [x.strip().upper() for x in symbols.split(",") if x.strip()][:100]
    with cursor(commit=False) as c:
        c.execute("select symbol, name from public.companies where symbol = any(%s::text[])", (syms,))
        names = dict(c.fetchall())
    sig = compute_signals([x for x in syms if x in names])
    items = [{**v, "name": names[k]} for k, v in sig.items()]
    items.sort(key=lambda x: _TAG_ORDER[x["primary"]])
    return {"items": items, "counts": _counts(items), "rules": SIGNAL_RULES}


# ---------------------------------------------------------------- holdings
class HoldingIn(BaseModel):
    symbol: str
    quantity: float = Field(ge=0)   # 0 = keep the company on your list, no position


@app.put("/holdings")
def put_holdings(items: list[HoldingIn], user: User = Depends(current_user)):
    syms = [i.symbol.upper().strip() for i in items]
    if len(set(syms)) != len(syms):
        raise HTTPException(422, "Duplicate symbols")
    with cursor() as c:
        c.execute("select symbol from public.companies where symbol = any(%s::text[])", (syms,))
        known = {r[0] for r in c.fetchall()}
        unknown = [s for s in syms if s not in known]
        if unknown:
            raise HTTPException(422, f"Not tracked yet: {unknown}")
        c.execute("delete from public.holdings where user_id = %s", (user.id,))
        for s, i in zip(syms, items):
            c.execute("insert into public.holdings (user_id, symbol, quantity) values (%s, %s, %s)",
                      (user.id, s, i.quantity))
        c.execute("delete from public.alerts where user_id = %s and not (symbol = any(%s::text[]))", (user.id, syms))
    run_alerts(lookback_days=30, user_id=user.id)
    return _portfolio(user.id)


@app.post("/holdings/reset")
def reset_holdings(user: User = Depends(current_user)):
    """Back to the seeded demo portfolio."""
    with cursor() as c:
        c.execute("delete from public.holdings where user_id = %s", (user.id,))
        c.execute("""insert into public.holdings (user_id, symbol, weight, quantity)
                     select %s, d.symbol, d.weight,
                            floor((d.weight / 100.0) * p.book_value / nullif(px.close, 0))
                     from public.demo_portfolio d
                     cross join (select book_value from public.profiles where user_id = %s) p
                     left join lateral (select close from public.prices_eod pe where pe.symbol = d.symbol
                                        order by date desc limit 1) px on true""", (user.id, user.id))
        c.execute("delete from public.alerts where user_id = %s", (user.id,))
    run_alerts(lookback_days=30, user_id=user.id)
    return _portfolio(user.id)


# --------------------------------------------------------------- companies
@app.get("/companies")
def companies(q: str = Query("", max_length=40), user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select symbol, name, sector, market_cap_cr from public.companies
                     where %s = '' or symbol ilike %s or name ilike %s
                     order by market_cap_cr desc nulls last limit 100""", (q, f"{q}%", f"%{q}%"))
        return [{"symbol": s, "name": n, "sector": sec, "market_cap_cr": float(m) if m else None}
                for s, n, sec, m in c.fetchall()]


@app.get("/prices/{symbol}")
def prices(symbol: str, days: int = Query(90, le=400), user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select date, close, volume from public.prices_eod
                     where symbol = %s and date >= current_date - %s::int order by date""", (symbol.upper(), days))
        rows = c.fetchall()
    if not rows:
        raise HTTPException(404, "No prices for symbol")
    return [{"date": str(d), "close": float(cl), "volume": int(v or 0)} for d, cl, v in rows]


@app.get("/filings/{filing_id}")
def filing(filing_id: int, user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        c.execute("""select f.id, f.symbol, co.name, f.filed_at, f.subject, f.note, f.url, f.category,
                            f.materiality, f.one_liner, f.enrichment, f.classified_by
                     from public.filings f join public.companies co using (symbol) where f.id = %s""", (filing_id,))
        r = c.fetchone()
    if not r:
        raise HTTPException(404, "Filing not found")
    keys = ["id", "symbol", "name", "filed_at", "subject", "note", "url", "category", "materiality",
            "one_liner", "enrichment", "classified_by"]
    d = dict(zip(keys, r))
    d["filed_at"] = d["filed_at"].isoformat()
    d["enrichment"] = _j(d["enrichment"])
    return d
