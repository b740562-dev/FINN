# FINN: Financial Investment Agent

A mobile-first agent for an investor running a portfolio of NSE stocks. It does two jobs:

- **Push:** tells you what changed across your holdings and why it matters. It ranks every exchange filing by materiality, turns results into numbers, gives new executives a bio, alerts you on moves you define as unusual, and folds routine paperwork away.
- **Pull:** research on any NSE company, grounded only in that company's own filings, annual reports and concall transcripts, with every claim cited.

> Point of view: an investor's scarce resource is attention. FINN's home screen is one ranked list. Every card has to earn its place and says why it's there ("Results · 7% of book", "raise = 4.3% of market cap"). Everything else is one tap away, collapsed.

---

## What's in the box

| Surface | What it does |
|---|---|
| **Today** | Ranked digest for 24h / 7d / 30d, plus **as-of replay** of any past date. Results cards show Revenue / EBITDA / PBT / PAT QoQ & YoY, margins in bp, and lenders get NII + NPAs. A management change shows the incoming person's bio with sources. Routine filings are collapsed. **60-second audio brief.** |
| **Alerts** | EOD price-move and volume-spike alerts against *your* thresholds (global + per-stock), with ₹ impact on your position. Filing alerts for the categories you choose. |
| **Research** | Any NSE ticker (fetched on demand). Four sections: Snapshot, Promise vs Delivered, Health check (trajectory, balance sheet, cash quality), Bull vs Bear. Every claim has a tap-to-source citation. Follow-up Q&A over the company's own documents. |
| **Ask Surya** | The round "Ask me" button (bottom left, on every screen) opens a full-screen chat ("Hello, I’m Surya, your investment guide…"). General guidance (debt, diversification, rebalancing) is free-form; **anything about a specific company's data comes only from verified material**: its own documents in FINN (annual reports, concalls, presentations, user uploads), its exchange-reported financials, and the Promise vs Delivered tracker. Every such claim is cited inline and its numbers are checked against the cited text; otherwise Surya says it doesn't have it and offers 📎 to add the matching report, which it reads in the background. |
| **You** | Define "unusual" (sliders, filing categories). Edit holdings and profile. **Log in with a 6-digit email code** (OTP); a guest's portfolio comes along, and verified accounts show a ✓ next to the name. **"How FINN thinks"** cost & routing meter, **admin-only** (`ADMIN_EMAILS`; the API returns 403 and strips model names for everyone else). |

## Architecture

```
            ┌──────────────── GitHub Actions (cron, 2-hourly on market days) ────────────────┐
            │ ingest (yfinance EOD + screener.in) → classify → results cards → bios → alerts │
            └──────────────────────────────────────┬──────────────────────────────────────────┘
                                                   ▼
Next.js PWA (Vercel) ──Bearer JWT──▶ FastAPI (Render) ──▶ Supabase Postgres + pgvector (RLS)
   Today · Alerts · Research · You        │      │                     ▲
   supabase-js auth (guest/email)         │      └── Gemini (routed) ──┘ llm_cache + llm_calls
                                          └── Tavily (exec bios only, push side)
```

- **Backend** `backend/finn/`: `sources/` (prices, screener), `push/` (classify, rank, results, bios, alerts), `pull/` (docs, retrieve, sections, ask, cite), `api/` (FastAPI), `jobs/` (ingest, pipeline), `llm.py` (routing + cache + cost log).
- **DB** `backend/sql/00x_*.sql`: shared market data (read-only to users) + per-user tables, all behind row-level security. A trigger seeds every new account, guests included, with the demo portfolio.
- **Frontend** `web/`: Next.js 16 App Router, client-rendered behind auth, hand-written "Terminal" design system (`app/globals.css`).

## Judgment calls (the short version)

1. **Rules before models.** BSE subject lines are standardised, so 58% of filings are classified by regex with zero LLM calls. The rest go to `gemini-3.5-flash-lite` in batches of 15.
2. **Materiality is computed in code, not by the model.** The model only *extracts* facts (₹ amount, people, rating action). Code sizes them against the company: order as % of TTM revenue, raise as % of market cap, litigation amount, rating direction, executive seniority. Every factor becomes the card's "why".
3. **No model touches a number the user sees.** Results cards are computed from the reported quarterly table. The text in the filing is **cross-checked** against them (ITC's "19% revenue growth" vs 3.9% in the table gets flagged, not hidden). Red flags (qualified audit opinion, exceptional items) are detected from filing text.
4. **One-liner number guard.** Every number in a generated one-liner must exist in the filing (unit conversions allowed within 0.5%). It caught a real 10× crore/million error.
5. **Grounded bios.** Incoming executives: one cached web search + one cheap summarisation restricted to the snippets. Every organisation and school must appear in the sources or it's dropped. Social media and aggregator links are filtered out.
6. **Pull side = primary sources only.** Screener's reported financials + the company's own annual reports and transcripts. No news, no broker notes, no model memory. Quotes are verified against the cited chunk before they're shown.
7. **Cost.**
   - Two model tiers: `gemini-3.5-flash-lite` for bulk, `gemini-3.6-flash` only for reasoning, with automatic fallback when a model is overloaded. `gemini-3.8-flash` is opt-in via `FINN_REASON_MODEL`, because it was timing out on our key.
   - A Postgres response cache means identical work is never paid twice.
   - Per-call logging is priced at Google's published rates and shown in-app.
   - **Everything built so far** (110 filings classified, 3 executive bios, research dossiers for 23 companies) **would cost $0.20 at paid rates**. It's ₹0 billed, on the free tier.
   - A pipeline run with nothing new costs zero LLM calls.
8. **Honest limits over fake completeness.** "Quiet day" instead of padding the feed, "pending" when a quarter isn't posted yet, "needs documents" instead of guessing management's guidance.

## Data sources & what we learned

- **Prices:** yfinance (`.NS`), end of day.
- **Filings, financials, document links:** screener.in. BSE's and NSE's own APIs and PDF hosts refuse non-browser clients, and we don't imitate browsers to get around that. So the announcement feed accumulates from screener's per-company list (latest 5, polled every 2h).
- **Annual reports and transcripts are uploaded**, either in-app or dropped into `backend/docs_inbox/<SYMBOL>/` as `AR-2026.pdf` / `CC-2026-11.pdf`.
  - Documents are shared by every user, so **only saved (non-guest) accounts can upload**. One bad upload shouldn't change everyone's research.
  - Uploads run as **background jobs** (read → index → analyse) that the app polls, so a 300-page annual report never hits a request timeout.
  - The job finishes by rebuilding Promise vs Delivered, so it's ready when the user looks.
  - **You → Data sources → Your documents:** pick the company, say what the document is (annual report, concall transcript, investor presentation) and where it came from (company website, BSE, NSE, investor relations, other, plus an optional link). The uploader can **remove** it later: its passages leave the index and the company's research is rebuilt without it.
- **Primary documents loaded:** BEL, TITAN, ASIANPAINT and KPITTECH each have 4 concall transcripts and their FY26 annual report (20 PDFs; annual reports trimmed to their ~120 most relevant pages). `scripts/doc_downloads.py` builds the click-list of BSE links and files the downloads automatically.
- **Research is pre-built.** After each refresh, `finn.pull.prewarm` rebuilds any company whose reported numbers or documents changed. Everything else stays cached, so no one waits on a cold dossier.
- **Exec bios:** Tavily search (push-side enrichment only; never used for research).
- **Network blocks:** some Indian ISPs block `*.supabase.co` (and render.com). The browser never calls Supabase directly. `/sb/*` on the app's own domain is rewritten server-side to the project (`web/next.config.ts`), so sign-in works on those networks too.

## Run locally

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # (bin/ on mac/linux)
cp .env.example .env              # fill GEMINI / SUPABASE / TAVILY keys
# save Supabase's CA cert as backend/supabase-ca.crt (Project Settings → Database → SSL)
.venv/Scripts/python scripts/migrate.py
.venv/Scripts/python -m finn.jobs.pipeline          # load data, classify, enrich, alert
.venv/Scripts/python -m finn.pull.docs              # ingest PDFs from docs_inbox/ (optional)
.venv/Scripts/python -m finn.pull.prewarm           # pre-build research pages (pipeline also does this)
.venv/Scripts/python -m uvicorn finn.api.main:app --host 127.0.0.1 --port 8000

# frontend
cd web
npm install
# web/.env.local: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run dev
```

Checks: `scripts/check_services.py` (Gemini + DB), `scripts/check_auth_seed.py` (guest sign-up → seeding → RLS), `scripts/check_api.py` (every endpoint, throwaway guest), `scripts/check_research.py` (research sections), `scripts/check_uploads.py` (guest block, background ingest job, duplicates; in-process, no Supabase call), `scripts/digest_preview.py 7` (print a digest).

## Deploy

1. **API → Render:** New → Blueprint → this repo (`render.yaml`). Enter the secrets. Set `FRONTEND_ORIGINS` to the Vercel URL and `ADMIN_EMAILS` to the account(s) that may see internals.
2. **Web → Vercel:** import repo, root directory `web/`, env `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` (Render URL). Add the Vercel URL to Supabase → Authentication → URL configuration.
3. **Scheduler → GitHub Actions:** repo secrets `DATABASE_URL`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`; repo variable `API_URL` (Render URL) for the keep-warm ping.

## Deliberately left out

Intraday data, broker/news feeds, web push notifications (alerts land in the in-app inbox), Google sign-in (wired, behind `NEXT_PUBLIC_GOOGLE_AUTH=1`), and automated PDF fetching from exchange hosts that block scripted clients.

See [DECISIONS.md](DECISIONS.md) for the full decision log and [docs/WRITEUP.md](docs/WRITEUP.md) for the submission write-up.
