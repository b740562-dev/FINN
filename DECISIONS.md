# FINN — Build Decisions

Deadline: **15 Nov 2026** · Budget: **~25–35 focused hours** · Principle: *thin-but-working beats broad-but-broken*

## 1. Product & interaction model
- **Home = ranked briefing feed + persistent "Ask FINN" bar.**
  - Top: window picker (24h default · 7d · 30d · custom) + **"as-of" date** to replay a rich week.
  - Headline: "N things matter today". Material cards first. Routine filings collapse into one "▸ 14 routine filings" row.
  - Every card has a **"why it's here" chip**, e.g. "Results · 8% of your portfolio".
- **Ask bar → Dossier** for any NSE ticker. It streams in section by section, with follow-up chat underneath.
- **Visual style: A · Terminal (dark, dense).** Reference: `mockups/home-feed-styles.html`.
  - Near-black background (#0a0c0f), cards #11151a with a 1px #1d2128 border.
  - JetBrains Mono for tickers, numbers and labels; Inter for prose. Tabular numerals everywhere.
  - Amber accent (#f0b43c). Green #3ddc84 for up, red #ff6b6b for down.
  - Each card has a colour strip on its left edge for its type: amber = results, blue = management, green = price/volume alert, purple = M&A.
  - "Why it's here" pill on every card. Routine filings collapse into one dashed row.
  - Ask bar is pinned above the tab bar (TODAY · ALERTS · RESEARCH · YOU).
- **Real user accounts (Supabase Auth): Google sign-in + email magic link.**
  - Every new account is **seeded with the demo portfolio** + default thresholds, so the feed is full on first open. Each user's edits, alerts and push subscriptions are their own.
  - Postgres Row Level Security scopes user data per account. The FastAPI backend verifies the Supabase JWT on each request.
  - Shared data (prices, filings, extracted results, RAG index, dossiers) is global and cached once for everyone. Only portfolio, settings and alert state are per user.
  - **"Try as guest"** button (Supabase anonymous sign-in) next to Google/email. One tap gives an instant account seeded with the demo portfolio, upgradable to Google/email later without losing settings. This is the primary call-to-action on the login screen, so graders get in with zero friction.
  - **Reset** (red, with confirm) sets every holding to 0 but keeps the companies on the list, so the user can type their own quantities, remove companies or add new ones. A company held at 0 stays a watchlist entry: its news still shows, ranked without position size.
- **Holdings carry quantity/weight.** This feeds the ranking and lets cards show impact lines like "this move cost you ₹1.2L / −0.8%".

## 1b. Demo portfolio (seeded into every new account)
**Revised 12 Nov: India's seven largest listed companies**, the names every investor knows, weighted by market cap like an index (market caps from screener, 12 Nov 2026).

| Ticker | Sector | Market cap (₹ cr) | Weight |
|---|---|---|---|
| RELIANCE | Conglomerate | 18.07 L | 22.5% |
| BHARTIARTL | Telecom | 13.16 L | 16.5% |
| HDFCBANK | Private bank | 12.45 L | 15.5% |
| ICICIBANK | Private bank | 11.29 L | 14% |
| SBIN | PSU bank | 9.80 L | 12% |
| TCS | IT services | 8.94 L | 11% |
| BAJFINANCE | NBFC | 6.69 L | 8.5% |

*(Tried and dropped the same day: the seven most widely held stocks by shareholder count (Tata Motors, Yes Bank, Vodafone Idea, Tata Steel, Suzlon, IRFC, Jio Financial). Widely held is not the same as well known.)*
*(First version, 11 Nov, 18 stocks: RELIANCE, HDFCBANK, INFY, ITC, LT, BHARTIARTL, SUNPHARMA, MARUTI, TATASTEEL, BAJFINANCE, ETERNAL, TRENT, DIXON, POLYCAB, PERSISTENT, SUZLON, CDSL, IEX. Replaced because a default portfolio should look like what people actually own.)*

Notional book value ₹50L, so quantities are derived from weight × ₹50L ÷ the latest close at seed time.
**Ad-hoc research set (pre-warmed):** BEL, TITAN, ASIANPAINT, KPITTECH. *(HAL swapped for BEL on 11 Nov: HAL had only 1 transcript in 13 months.)*
**Data check:** every default ticker loads prices (yfinance) and reported financials (screener). ITC holds no concalls, so its pull view runs numbers-only and shows a "no transcripts" state.
Any ticker that fails the data check (yfinance prices / screener transcripts) is swapped for a same-sector peer.

## 2. Push (all four in scope)
| Feature | Approach |
|---|---|
| Windowed digest | Every filing across the portfolio in the chosen window, ranked, routine ones collapsed, one-liner only where it earns attention |
| Price/volume alerts | Configurable globally and per stock. Defaults: volume > 2× 20-day avg, \|move\| > 5%. Evaluated on EOD data |
| Results first-cut | Results PDF → Revenue / EBITDA / PBT / PAT + margins, QoQ & YoY, as a compact table card. Cross-checked against screener once it updates |
| Mgmt-change bios | Extract the profile from the filing itself (SEBI LODR requires one) → enrich with a free search API (Tavily/Brave) → 2–3 lines with source links |

**Ranking score** = category base weight + LLM materiality nudge + the user's chosen "categories I care about" + position weight.
**Classification:** BSE/NSE's own category/subcategory and keyword rules first. The LLM is called only for ambiguous filings.
**Delivery:** in-app alerts inbox + **web push** from the PWA (Android works directly; iOS needs Add to Home Screen). Tapping a notification opens the card.

## 3. Pull (all four blocks, built in this order)
1. **Snapshot**: business (segments, revenue mix) + financial (headline numbers, margins, ratios)
2. **Promise vs Delivered** ⭐: guidance from the last 4 concalls vs reported actuals, as a hit/partial/miss scorecard with cited quotes. Covers *Guidance* + *Narrative vs numbers*
3. **Health check**: trajectory, balance sheet (debt, D/E, working-capital cycle), cash quality (CFO vs PAT, FCF). Sparklines + one verdict line each
4. **Bull vs Bear**: 3 points each way, every point tied to a cited fact

- **Grounding:** every claim cites a chunk (doc, page, quote). A verifier pass (string match + cheap model) drops unsupported claims. The UI says **"Not disclosed"** instead of guessing. No news, broker notes, or model memory.
- **Any ticker:** resolve → scrape screener for the latest AR + last 4 transcripts → download, chunk, embed → analyse. Live progress steps, ~1–3 min the first time, instant from cache after that. The demo set is pre-warmed.
- **Retrieval:** classic RAG (pgvector). Promise-vs-Delivered also runs **targeted per-quarter retrieval queries** ("guidance", "outlook", "target", "margin", "capex") so the comparison is systematic.

## 4. Data sources (revised 11 Nov after probing)
**What we found:**
- BSE's announcements API redirects non-browser clients to an error page.
- Every BSE-hosted PDF returns 403.
- NSE (API and RSS archives) times out.

We only use sources that serve a plainly identified client. We don't imitate browsers or automate past bot protection.

- **EOD prices:** yfinance (`.NS`), 20-day volume average computed in-house. ✅ Verified on all 22 tickers.
- **Filings index:** screener.in shows the 5 latest announcements per company. Each comes with its BSE subject line, a timestamp, the exchange PDF link and a short note.
  - A cron polls it every few hours and **accumulates history in the DB**, so the 7d/30d windows fill up from first run onward. Dedupe is on (symbol, timestamp, subject).
  - Classification works off the standardised BSE subject lines (e.g. "Regulation 30 (LODR)-Credit Rating"). The LLM is called only when the subject is ambiguous.
  - The PDF link is shown as "Open filing", which works in the user's browser.
- **Results first-cut:** Revenue / EBITDA (screener's "Operating Profit") / PBT / PAT, QoQ & YoY, from screener's quarterly table. It's compiled from the results filing, so we label it "from results filing via screener". Lenders map to Revenue / Financing Profit / PBT / PAT.
- **Mgmt bios:** person + role pulled from the announcement subject/note → web search (Tavily/Brave) → 2–3 line bio with sources. Falls back to "Profile not yet available" plus the filing link.
- **Numbers (pull):** screener tables. ✅ 13 quarters + 9–13 yrs P&L/BS/CF for all 22.
- **Docs (pull):** transcript/AR PDFs **uploaded** to FINN: pre-loaded for the demo set (you download them once in a browser), plus an in-app "Add document" upload for any ticker.
  - Unseen tickers still get the numbers-based sections immediately: Snapshot (financial part), Health check, and a numbers-only Bull/Bear.
  - The document-based sections (Promise vs Delivered, business mix) show "Add transcripts to unlock".
- **Freshness:** GitHub Actions cron ingests EOD prices and filings and runs the LLM once per filing. Results are cached by filing ID / PDF hash. A seeded snapshot is the fallback.

## 5. Stack
| Layer | Choice |
|---|---|
| Frontend | Next.js PWA on Vercel |
| Backend | Python FastAPI on Render free tier + keep-warm ping |
| DB | Supabase Postgres + pgvector (keep-alive ping so the project doesn't pause) |
| Auth | Supabase Auth: Google OAuth + email magic link + guest (anonymous sign-in), RLS on user tables |
| Scheduler | GitHub Actions cron |
| LLMs | Verified on our key (11 Nov). The 2.5 models are closed to new users, and no Pro text model is available.<br>• Bulk work (classification, one-liners, extraction, quote verification): **`gemini-3.5-flash-lite`**<br>• Reasoning (Promise vs Delivered, Bull/Bear, chat synthesis): **`gemini-3.6-flash`**. Planned as `gemini-3.8-flash`, but on 11 Nov it returned 504s and multi-minute waits on this key, so it is opt-in via `FINN_REASON_MODEL`. `gemini-3.5-flash` is deprecated and Google routes it to 3.6-flash, so we name 3.6 directly.<br>• Automatic fallback on 429/503/504: 3.6-flash → 3.5-flash-lite → 3.1-flash-lite<br>• Paid-tier prices (USD per 1M tokens in/out, until 31 Dec 2026): flash-lite 0.30/2.50, 3.6-flash 0.75/3.75, embedding-2 0.20. Free tier: ₹0.<br>• Embeddings: **`gemini-embedding-2`**, truncated to 768 dims (pgvector HNSW indexes cap at 2000) |
| DB driver | `pg8000` (pure Python). Windows Smart App Control blocks psycopg's bundled libpq DLL. TLS is always verified against Supabase's CA (`backend/supabase-ca.crt`) |
| Search | Tavily/Brave free tier (bios only) |

## 6. Key assumptions
- **EOD only.** Here "the moment it crosses a threshold" means the next ingest run after market close (~16:00–18:00 IST), not intraday.
- Financials are **consolidated** where available, otherwise standalone. Units are ₹ crore. Indian fiscal year (Apr–Mar), quarters labelled like "Q2 FY27".
- **Banks/NBFCs:** EBITDA doesn't apply. Map to NII / Pre-provision operating profit and label them clearly.
- Push-side enrichment (bios) may use web search. Pull side is primary sources only.
- Render free tier has 512 MB RAM → parse PDFs page by page (PyMuPDF), never load a whole AR into memory.
- Free-tier rate limits → cache everything, precompute the demo set, queue LLM calls.

## 7. Extras (only after core push + pull work end to end)
- **Cost & routing meter**: per insight, which model, tokens, ₹ cost, cache hit. *(Revised 14 Nov: removed from the app for everyone, because it's operator information. Costs stay logged in `llm_calls` and readable by admins via `GET /usage`.)*
- **60-sec audio brief**: browser TTS of today's top items
- **Voice questions**: hold-to-talk on the ask bar (Web Speech API)

## 8. Rough build plan
| Day | Focus |
|---|---|
| 11–12 Nov | Portfolio list ✔ · 2 mockups → pick style · repo scaffold · Supabase schema · ingestion (yfinance, BSE, NSE, screener) · classification + ranking |
| 12–13 Nov | Push UI: digest, cards, results first-cut, mgmt bios, alerts + web push · deploy early |
| 13–14 Nov | Pull: RAG pipeline, Snapshot → Promise vs Delivered → Health → Bull/Bear, citations + verifier, follow-up chat |
| 14–15 Nov | Extras, polish, phone testing, README, covering-email writeup, export AI build history |

## 9. Still open
- [ ] API keys needed: Gemini, Supabase, Tavily (or Brave), Google OAuth client ID (Google Cloud console), VAPID keys for web push (generated locally)


## Surya chat and email OTP (12 Nov)
- **Surya** is the conversational layer. The rule the user set ("general advice is fine, data only from verified documents") is enforced in code, not just in the prompt:
  - companies are detected deterministically (symbol / name / unique first word; "Adani Green" is not mistaken for Adani Enterprises);
  - retrieval is topic-focused (company name and question words stripped, latest concall when asked, exchange cover letters filtered out);
  - verified material = the company's documents, its exchange-reported financials, and the Promise vs Delivered tracker;
  - every c# quote must occur in its chunk, unknown markers are stripped, and every number in a company answer must appear in the cited material (PDF number spacing normalised first). If not, the answer is replaced by "I don't have that in a verified document yet, add the matching report".
- **Email log-in is a one-time code**, not a magic link. A guest who logs in attaches the email to their own account (`updateUser` + `verifyOtp(type=email_change)`), so portfolio and settings carry over; if the email already has an account, they sign in to that one. Supabase's email templates must include `{{ .Token }}`.
- Guests show a generic person avatar and the name "Guest", with **Log in** above the date on Today and next to Edit profile on You.

## Automatic report pickup (12 Nov)
- **Problem:** research depended on someone uploading annual reports and transcripts by hand.
- **Probe:** for 41 companies, the latest transcript, presentation and annual report links on screener came to 99 links. 90 point to BSE, which returned 403 to FINN's honest client for every one. Company-website and NSE-archive links downloaded fine.
- **Decision:** automate everything that can be fetched honestly, and turn the rest into a one-tap task. We do not imitate browsers.
  1. **Detect:** ingest records every recent report as a candidate from the screener page it already fetches, so this costs no extra requests.
  2. **Download:** directly if the host allows, else find the same PDF on the company's own investor-relations page, matching document type plus month and year.
  3. **Index:** then rebuild the research, and add the report's key takeaway to Top news as a ranked item: concall 55, annual report 50, presentation 45. The takeaway's numbers must appear in the document, and the item is dated by publication. Revised 14 Nov: no "report is out" alert, because the content is what matters, not the event.
  4. **Otherwise mark it `needs_upload`:** it shows under Research → New reports and in Surya ("Q2 FY27 concall is out but not read yet"), with an upload form pre-filled except for the PDF. Any logged-in user can do it. Uploads settle the matching candidate.
- **Production path:** a licensed exchange or vendor feed (BSE/NSE data products, or vendors) makes this fully hands-off.
