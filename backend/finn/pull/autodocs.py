"""Automatic pickup of new primary documents (concall transcripts, investor
presentations, annual reports).

  1. record()  - called from ingest with the screener page it already fetched:
                 notes every recently published report as a candidate.
  2. fetch_pending() - for each new candidate, downloads it with FINN's honest,
                 self-identifying client when the host serves plain clients
                 (company websites, some NSE archives). BSE refuses such clients,
                 so for BSE-only links FINN looks for the same document on the
                 company's own investor-relations page first. Downloaded PDFs are
                 indexed, the company's research is rebuilt, and holders get an
                 alert. Anything still out of reach is marked needs_upload and
                 offered in the app as a one-tap, pre-filled upload. Each report
                 read enters the feed (Top news) with its own key takeaway.

We never imitate a browser to get past a site's bot protection.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from finn.db import cursor
from finn.http import make_session
from finn.pull.docs import doc_label, ingest_pdf

BLOCKED_HOSTS = ("bseindia.com",)        # refuses non-browser clients (verified 12 Nov 2026: 90/90 = 403)
MAX_PDF = 40 * 1024 * 1024
RECENT_DAYS = 400                        # transcripts/presentations older than ~13 months aren't worth chasing
PER_RUN = 12                             # politeness: candidates attempted per scheduler run
RETRY_AFTER = timedelta(hours=20)        # re-check needs_upload items about once a day
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_session = make_session({"Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5"})


# ------------------------------------------------------------------ discover
def record(symbol: str, page) -> int:
    """Upsert candidates from a parsed screener CompanyPage. Returns how many are new."""
    today = date.today()
    found: list[tuple[str, date, str]] = []
    for cc in page.concalls[:4]:
        if not cc.date:
            continue
        d = date.fromisoformat(cc.date)
        if (today - d).days > RECENT_DAYS:
            continue
        if cc.transcript_url:
            found.append(("transcript", d, cc.transcript_url))
        if cc.ppt_url:                       # non-PDF links fail the %PDF check and wait for upload
            found.append(("presentation", d, cc.ppt_url))
    if page.annual_reports and page.annual_reports[0].year:
        a = page.annual_reports[0]
        found.append(("annual_report", date(a.year, 3, 31), a.url))

    new = 0
    with cursor() as c:
        if getattr(page, "website", None):
            c.execute("update public.companies set website = %s where symbol = %s", (page.website, symbol))
        for kind, period, url in found:
            # Already in the library? (uploaded by someone, or the demo set)
            c.execute("""select id from public.documents where symbol = %s and kind = %s
                           and date_trunc('month', period) = date_trunc('month', %s::date)
                         order by id desc limit 1""", (symbol, kind, period))
            doc = c.fetchone()
            c.execute("""insert into public.report_candidates (symbol, kind, period, label, url, status, document_id, via)
                         values (%s, %s, %s, %s, %s, %s, %s, %s)
                         on conflict (symbol, kind, period) do update
                           set url = case when report_candidates.status in ('new', 'needs_upload', 'failed')
                                          then excluded.url else report_candidates.url end,
                               status = case when excluded.status = 'ingested' then 'ingested'
                                             else report_candidates.status end,
                               document_id = coalesce(report_candidates.document_id, excluded.document_id),
                               updated_at = case when excluded.status = 'ingested' and report_candidates.status <> 'ingested'
                                                 then now() else report_candidates.updated_at end
                         returning (xmax = 0)""",
                      (symbol, kind, period, doc_label(kind, period), url,
                       "ingested" if doc else "new", doc[0] if doc else None, "existing" if doc else None))
            if c.fetchone()[0] and not doc:
                new += 1
    return new


# ------------------------------------------------------------------ fetch
def _download(url: str) -> bytes | None:
    try:
        r = _session.get(url, timeout=30, stream=True, allow_redirects=True)
        if r.status_code != 200:
            r.close()
            return None
        buf = bytearray()
        for chunk in r.iter_content(64 * 1024):
            buf.extend(chunk)
            if len(buf) > MAX_PDF:
                r.close()
                return None
        r.close()
        return bytes(buf) if buf[:4] == b"%PDF" else None
    except Exception:
        return None


def _blocked(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS)


def _ir_pages(website: str) -> list[str]:
    """The company's own investor-relations pages (same site), from its homepage."""
    try:
        r = _session.get(website, timeout=20)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    base = urlparse(r.url).netloc.split(":")[0].removeprefix("www.")
    pages = []
    for m in re.finditer(r'href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', r.text, re.I | re.S):
        href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2)).lower()
        u = urljoin(r.url, href)
        if base not in urlparse(u).netloc:
            continue
        if re.search(r"investor", href, re.I) or "investor" in text:
            if u not in pages:
                pages.append(u)
    return pages[:3]


def _matches(kind: str, period: date, text: str) -> bool:
    t = text.lower()
    y4, y2 = str(period.year), str(period.year)[-2:]
    if kind == "annual_report":
        prev = str(period.year - 1)
        return "annual" in t and "report" in t and (
            f"fy{y2}" in t or f"{prev}-{y2}" in t or f"{prev}-{y4}" in t or f"{prev}_{y2}" in t or y4 in t)
    word = "transcript" if kind == "transcript" else "presentation"
    if word not in t and not (kind == "presentation" and ("ppt" in t or "deck" in t)):
        return False
    mon = MONTHS[period.month - 1]
    return (mon in t and (y4 in t or y2 in t)) or period.strftime("%Y%m") in t.replace("-", "").replace("_", "")


def _from_company_site(website: str | None, kind: str, period: date) -> str | None:
    """Find the same document on the company's IR page(s): a PDF whose link text
    or address names the document type and its month/year."""
    if not website:
        return None
    for page_url in _ir_pages(website):
        try:
            r = _session.get(page_url, timeout=20)
            if r.status_code != 200:
                continue
        except Exception:
            continue
        for m in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]*>(.*?)</a>', r.text, re.I | re.S):
            href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
            u = urljoin(r.url, href)
            if _blocked(u):
                continue
            if _matches(kind, period, f"{text} {u}"):
                return u
        time.sleep(0.5)
    return None


# How much a freshly published report matters in the feed (same 0-100 scale as
# filings; >= 35 makes Top news). A concall carries management's latest view.
REPORT_MATERIALITY = {"transcript": 55, "annual_report": 50, "presentation": 45}
REPORT_QUERY = {
    "transcript": "outlook guidance expect growth margin demand next quarter year",
    "annual_report": "performance highlights revenue profit growth strategy outlook order book",
    "presentation": "highlights growth guidance key metrics outlook",
}
TAKEAWAY_SCHEMA = {"type": "object", "properties": {"takeaway": {"type": "string"}}, "required": ["takeaway"]}


def _takeaway(symbol: str, kind: str, label: str, doc_id: int) -> str | None:
    """The single most decision-relevant line from the report itself, using only
    its own text. Numbers must appear in the excerpts or the line is dropped."""
    from finn import llm
    from finn.pull.chat import _BOILER
    from finn.pull.retrieve import search
    from finn.push.classify import numbers_grounded

    chunks = [c for c in search(symbol, REPORT_QUERY[kind], k=14, document_ids=[doc_id])
              if not _BOILER.search(c.content[:600]) and len(c.content) > 200][:6]
    if not chunks:
        return None
    text = "\n\n".join(f"(p.{c.page}) {c.content[:1500]}" for c in chunks)
    out = llm.generate_json(
        "report_takeaway",
        f"Company: {symbol}. Document: {label}.\nEXCERPTS\n{text}\n\n"
        "Write the ONE most decision-relevant takeaway for an investor, in at most 22 words, plain English. "
        "Prefer forward-looking guidance or a material change. Use ONLY these excerpts; include a number only "
        "if it appears in them. No preamble, no company name at the start.",
        TAKEAWAY_SCHEMA, model=llm.BULK, thinking="low", ref_type="document", ref_id=str(doc_id))
    line = (out.get("takeaway") or "").strip().rstrip(".") + "."
    norm = re.sub(r"(?<=\d)\s*,\s*(?=\d{2,3}\b)", ",", text)
    return line if len(line) > 12 and numbers_grounded(line, norm) else None


def publish(symbol: str, kind: str, label: str, document_id: int, url: str | None) -> bool:
    """Put a newly read report into the feed as a normal item, ranked by how much
    it matters, with what it actually says. No separate "report is out" alert."""
    with cursor(commit=False) as c:
        c.execute("select 1 from public.filings where dedupe_key = %s", (f"report:{document_id}",))
        if c.fetchone():
            return False
        c.execute("select ingested_at, period from public.documents where id = %s", (document_id,))
        row = c.fetchone()
    if not row:
        return False
    ingested, period = row
    # Date it by when it was published, so a backlog report never poses as fresh news:
    # concalls/presentations by their call month; an annual report only counts while it's
    # the current year's (published within ~7 months of its financial year end).
    if kind == "annual_report":
        if period is None or (date.today() - period).days > 215:
            return False
        when = ingested
    elif period is None:
        when = ingested
    else:
        # The exact day the company filed it on the exchange, when FINN has that filing;
        # otherwise mid-month of the call.
        pat = "%transcript%" if kind == "transcript" else "%presentation%"
        with cursor(commit=False) as c:
            c.execute("""select min(filed_at) from public.filings
                         where symbol = %s and category is distinct from 'report' and subject ilike %s
                           and filed_at >= %s::date and filed_at < (%s::date + interval '45 days')""",
                      (symbol, pat, period, period))
            exact = c.fetchone()[0]
        when = exact or datetime(period.year, period.month, 15, 12, tzinfo=timezone.utc)
    try:
        line = _takeaway(symbol, kind, label, document_id)
    except Exception:
        line = None
    word = {"transcript": "concall", "annual_report": "annual report", "presentation": "investor presentation"}[kind]
    with cursor() as c:
        c.execute("""insert into public.filings (symbol, filed_at, subject, note, url, category, materiality,
                                                 one_liner, enrichment, classified_by, dedupe_key)
                     values (%s, %s, %s, null, %s, 'report', %s, %s, %s::jsonb, 'report', %s)
                     on conflict (dedupe_key) do nothing""",
                  (symbol, when, f"{label} ({word})", url, REPORT_MATERIALITY[kind],
                   f"{label}: {line}" if line else None,
                   json.dumps({"factors": [f"new {word}"], "document_id": document_id, "report_kind": kind}),
                   f"report:{document_id}"))
        return c.rowcount > 0


def announce(symbol: str, label: str, document_id: int, url: str | None, kind: str | None = None) -> bool:
    """Kept for the upload path: a user-added report also enters the feed."""
    with cursor(commit=False) as c:
        c.execute("select kind, label from public.documents where id = %s", (document_id,))
        r = c.fetchone()
    if not r:
        return False
    return publish(symbol, kind or r[0], r[1] or label, document_id, url)


def fetch_pending(limit: int = PER_RUN, rebuild: bool = True) -> dict:
    """Try to obtain new candidates automatically. Returns run stats."""
    from finn.pull import sections as S

    with cursor(commit=False) as c:
        c.execute("""select rc.id, rc.symbol, rc.kind, rc.period, rc.label, rc.url, co.website
                     from public.report_candidates rc join public.companies co using (symbol)
                     where rc.status = 'new'
                        or (rc.status = 'needs_upload' and rc.attempts < 5 and rc.updated_at < now() - %s::interval)
                     order by rc.period desc limit %s""", (f"{int(RETRY_AFTER.total_seconds())} seconds", limit))
        todo = c.fetchall()

    stats = {"checked": len(todo), "ingested": 0, "needs_upload": 0, "failed": 0, "feed": 0}
    touched: set[str] = set()
    for cid, sym, kind, period, label, url, website in todo:
        data, got, via = None, None, None
        if not _blocked(url):
            data = _download(url)
            got, via = url, "direct"
        if data is None:
            alt = _from_company_site(website, kind, period)
            if alt:
                data = _download(alt)
                got, via = alt, "company_site"
        with cursor() as c:
            if data is None:
                c.execute("""update public.report_candidates set status = 'needs_upload', attempts = attempts + 1,
                               last_error = %s, updated_at = now() where id = %s""",
                          ("host refuses non-browser clients" if _blocked(url) else "not downloadable", cid))
                stats["needs_upload"] += 1
                continue
        host = urlparse(got).netloc.lower()
        source = "nse" if "nseindia" in host else "company_website"
        try:
            res = ingest_pdf(sym, data, kind, period, filename=f"auto-{kind}-{period:%Y-%m}.pdf",
                             source=source, source_url=got)
        except Exception as e:  # unreadable PDF (scanned), etc.
            with cursor() as c:
                c.execute("""update public.report_candidates set status = 'failed', attempts = attempts + 1,
                               last_error = %s, updated_at = now() where id = %s""", (str(e)[:200], cid))
            stats["failed"] += 1
            continue
        with cursor() as c:
            c.execute("""update public.report_candidates set status = 'ingested', via = %s, fetched_url = %s,
                           document_id = %s, last_error = null, updated_at = now() where id = %s""",
                      (via, got, res["document_id"], cid))
        if res["status"] == "ingested":
            stats["feed"] += int(publish(sym, kind, label, res["document_id"], got))
        stats["ingested"] += 1
        touched.add(sym)
        time.sleep(0.5)

    if rebuild:
        for sym in touched:            # research reflects the new document right away
            S.invalidate(sym)
            for sec in ("snapshot", "promise_delivered", "bull_bear"):
                try:
                    S.get_section(sym, sec)
                except Exception:
                    pass
    stats["companies_rebuilt"] = sorted(touched)
    return stats


def mark_uploaded(symbol: str, kind: str, period: date, document_id: int) -> None:
    """A user uploaded a document: settle the matching candidate (same company, type and month)."""
    with cursor() as c:
        c.execute("""update public.report_candidates set status = 'ingested', via = coalesce(via, 'upload'),
                       document_id = %s, updated_at = now()
                     where symbol = %s and kind = %s
                       and date_trunc('month', period) = date_trunc('month', %s::date)
                       and status <> 'ingested'""", (document_id, symbol, kind, period))


def pending_for(symbols: list[str] | None = None, *, include_recent_auto: bool = True) -> list[dict]:
    """Reports waiting for a one-tap upload (newest first), plus ones FINN picked
    up on its own in the last week so the app can show the automation working."""
    q = """select rc.id, rc.symbol, co.name, rc.kind, rc.period, rc.label, rc.url, rc.status, rc.via,
                  rc.fetched_url, rc.discovered_at, rc.updated_at
           from public.report_candidates rc join public.companies co using (symbol)
           where (rc.status = 'needs_upload'
                  or (%s and rc.status = 'ingested' and rc.via in ('direct', 'company_site')
                      and rc.updated_at > now() - interval '7 days'))"""
    args: list = [include_recent_auto]
    if symbols is not None:
        q += " and rc.symbol = any(%s::text[])"
        args.append(symbols)
    q += " order by (rc.status = 'needs_upload') desc, rc.period desc limit 50"
    with cursor(commit=False) as c:
        c.execute(q, args)
        rows = c.fetchall()
    out = []
    for cid, sym, name, kind, period, label, url, status, via, fetched, disc, upd in rows:
        out.append({"id": cid, "symbol": sym, "name": name, "kind": kind, "period": period.isoformat(),
                    "label": label, "url": url, "host": urlparse(url).netloc.removeprefix("www."),
                    "status": status, "via": via, "fetched_url": fetched,
                    "discovered_at": disc.isoformat(), "updated_at": upd.isoformat()})
    return out


if __name__ == "__main__":
    print(fetch_pending())
