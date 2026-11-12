"""screener.in company page: standardised financial tables, document links
(annual reports, concall transcripts/decks), recent exchange announcements,
and the BSE/NSE identifiers. Works for any listed company screener covers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from finn.http import make_session, get

BASE = "https://www.screener.in"
TABLE_SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]

_session = make_session()


@dataclass
class Table:
    columns: list[str]
    rows: dict[str, list[float | None]]


@dataclass
class Announcement:
    title: str
    date: str | None          # ISO datetime from the page
    url: str
    note: str                 # screener's short line under the title (may be empty)


@dataclass
class AnnualReport:
    label: str                # e.g. "Annual Report 2026"
    year: int | None
    url: str


@dataclass
class Concall:
    period: str               # e.g. "Nov 2026"
    date: str | None          # first of that month, ISO
    transcript_url: str | None
    ppt_url: str | None
    recording_url: str | None


@dataclass
class CompanyPage:
    symbol: str
    name: str
    screener_id: str | None
    bse_code: str | None
    nse_symbol: str | None
    basis: str                # "consolidated" | "standalone"
    market_cap_cr: float | None = None
    website: str | None = None        # the company's own site (for investor-relations fallbacks)
    tables: dict[str, Table] = field(default_factory=dict)
    announcements: list[Announcement] = field(default_factory=list)
    annual_reports: list[AnnualReport] = field(default_factory=list)
    concalls: list[Concall] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _num(text: str) -> float | None:
    t = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    if t in ("", "-", "—"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_table(section: Tag | None) -> Table | None:
    if section is None:
        return None
    table = section.select_one("table.data-table") or section.select_one("table")
    if table is None:
        return None
    cols = [th.get_text(" ", strip=True) for th in table.select("thead th")][1:]
    rows: dict[str, list[float | None]] = {}
    for tr in table.select("tbody tr"):
        tds = tr.select("td")
        if not tds:
            continue
        label = re.sub(r"\s*\+\s*$", "", tds[0].get_text(" ", strip=True)).strip()
        if not label or label.lower().startswith("raw pdf"):
            continue
        rows[label] = [_num(td.get_text(" ", strip=True)) for td in tds[1:]]
    if not cols or not rows:
        return None
    return Table(columns=cols, rows=rows)


def _period_to_date(period: str) -> str | None:
    try:
        return datetime.strptime(period.strip(), "%b %Y").date().isoformat()
    except ValueError:
        return None


def _parse_documents(soup: BeautifulSoup, page: CompanyPage) -> None:
    docs = soup.select_one("section#documents")
    if docs is None:
        return
    for block in docs.select("div.documents"):
        heading = (block.find("h3") or block.find("h4"))
        title = heading.get_text(strip=True).lower() if heading else ""
        items = block.select("ul.list-links li")
        if title.startswith("announcements"):
            for li in items:
                a = li.find("a", href=True)
                if not a:
                    continue
                # The date line is a <div> (with a note) or a <span> (date only).
                t = a.find("time")
                when = t.get("datetime") if t else None
                sub = t.find_parent(["div", "span"]) if t else None
                note = ""
                if sub is not None and sub is not a:
                    note = re.sub(r"^\s*\d{1,2}\s+\w{3}(\s+\d{4})?\s*(-\s*)?", "", sub.get_text(" ", strip=True))
                    sub.extract()
                page.announcements.append(Announcement(
                    title=a.get_text(" ", strip=True), date=when, url=a["href"], note=note))
        elif title.startswith("annual reports"):
            for li in items:
                a = li.find("a", href=True)
                if not a:
                    continue
                label = a.get_text(" ", strip=True)
                m = re.search(r"(19|20)\d{2}", label)
                page.annual_reports.append(AnnualReport(
                    label=label, year=int(m.group(0)) if m else None, url=a["href"]))
        elif title.startswith("concalls"):
            for li in items:
                period_el = li.find("div")
                period = period_el.get_text(" ", strip=True) if period_el else ""
                links = {a.get_text(" ", strip=True).lower(): a["href"] for a in li.select("a[href]")}
                transcript = next((u for k, u in links.items() if "transcript" in k), None)
                page.concalls.append(Concall(
                    period=period, date=_period_to_date(period),
                    transcript_url=transcript, ppt_url=links.get("ppt"), recording_url=links.get("rec")))


def _parse(symbol: str, html: str, basis: str) -> CompanyPage:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    sid = re.search(r"/announcements/recent/(\d+)/", html)
    bse = soup.select_one("a[href*='bseindia.com/stock-share-price']")
    nse = soup.select_one("a[href*='nseindia.com/get-quotes/equity']")
    page = CompanyPage(
        symbol=symbol,
        name=h1.get_text(" ", strip=True) if h1 else symbol,
        screener_id=sid.group(1) if sid else None,
        bse_code=(re.search(r"/(\d{6})/?$", bse["href"]).group(1) if bse and re.search(r"/(\d{6})/?$", bse["href"]) else None),
        nse_symbol=(re.search(r"symbol=([^&]+)", nse["href"]).group(1) if nse else None),
        basis=basis,
    )
    site = next((x["href"] for x in soup.select("a[href^='http']") if x.get_text(strip=True).lower() == "website"), None)
    page.website = site
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        if name and name.get_text(strip=True).lower().startswith("market cap"):
            val = li.select_one(".number")
            page.market_cap_cr = _num(val.get_text(strip=True)) if val else None
    for sec in TABLE_SECTIONS:
        t = _parse_table(soup.select_one(f"section#{sec}"))
        if t:
            page.tables[sec] = t
    _parse_documents(soup, page)
    return page


def fetch_company(symbol: str, cache_ttl: int = 6 * 3600) -> CompanyPage:
    """Prefer consolidated figures; fall back to standalone when the
    consolidated view has no quarterly data."""
    html = get(_session, f"{BASE}/company/{symbol}/consolidated/", cache_ttl=cache_ttl).text
    page = _parse(symbol, html, "consolidated")
    if "quarters" not in page.tables or not any(
        v is not None for vals in page.tables["quarters"].rows.values() for v in vals
    ):
        html = get(_session, f"{BASE}/company/{symbol}/", cache_ttl=cache_ttl).text
        page = _parse(symbol, html, "standalone")
    return page
