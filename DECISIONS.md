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
  - "Reset to demo portfolio" option in settings.
- **Holdings carry quantity/weight.** This feeds the ranking and lets cards show impact lines like "this move cost you ₹1.2L / −0.8%".

## 1b. Demo portfolio (approved; seeded into every new account)
| Ticker | Sector | Size | Weight |
|---|---|---|---|
| RELIANCE | Conglomerate | Large | 10% |
| HDFCBANK | Private bank | Large | 10% |
| INFY | IT services | Large | 8% |
| ITC | FMCG | Large | 7% |
| LT | Capital goods | Large | 7% |
| BHARTIARTL | Telecom | Large | 7% |
| SUNPHARMA | Pharma | Large | 5% |
| MARUTI | Auto | Large | 5% |
| TATASTEEL | Metals | Large | 5% |
| BAJFINANCE | NBFC | Large | 5% |
| ETERNAL | Internet / delivery | Large | 4.5% |
| TRENT | Retail | Large | 5% |
| DIXON | Electronics manufacturing | Mid | 4% |
| POLYCAB | Cables | Mid | 4% |
| PERSISTENT | IT (mid) | Mid | 4% |
| SUZLON | Renewables | Mid | 3.5% |
| CDSL | Capital markets | Mid | 3% |
| IEX | Power exchange | Small–mid | 3% |

Notional book value ₹50L, so quantities are derived from weight × ₹50L ÷ the latest close at seed time.
**Ad-hoc research set (pre-warmed):** BEL, TITAN, ASIANPAINT, KPITTECH. *(HAL swapped for BEL on 11 Nov: HAL had only 1 transcript in 13 months.)*
**Data check (11 Nov):** all 22 tickers have prices + 13 quarters + 9–13 yrs P&L on screener. ITC and TRENT hold no concalls, so their pull view runs numbers-only and shows a "no transcripts" state. CDSL is NSE-only (no BSE code).
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
| LLMs | Gemini **Flash-Lite/Flash** for bulk work (classification, one-liners, extraction, verification) · Gemini **Pro** only for reasoning (Promise vs Delivered, Bull/Bear, chat synthesis) · Gemini embeddings |
| Search | Tavily/Brave free tier (bios only) |

## 6. Key assumptions
- **EOD only.** Here "the moment it crosses a threshold" means the next ingest run after market close (~16:00–18:00 IST), not intraday.
- Financials are **consolidated** where available, otherwise standalone. Units are ₹ crore. Indian fiscal year (Apr–Mar), quarters labelled like "Q2 FY27".
- **Banks/NBFCs:** EBITDA doesn't apply. Map to NII / Pre-provision operating profit and label them clearly.
- Push-side enrichment (bios) may use web search. Pull side is primary sources only.
- Render free tier has 512 MB RAM → parse PDFs page by page (PyMuPDF), never load a whole AR into memory.
- Free-tier rate limits → cache everything, precompute the demo set, queue LLM calls.

## 7. Extras (only after core push + pull work end to end)
- **Cost & routing meter**: per insight, which model, tokens, ₹ cost, cache hit
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
