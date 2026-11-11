# FINN: submission write-up (draft for the covering email)

## What I built

FINN is a mobile-first PWA for an investor holding a portfolio of NSE stocks. It has one opinion about interaction: **the investor's scarce resource is attention, so the home screen is a single ranked list where every card has to justify itself.**

- **Push.** A daily digest for any window (24h / 7d / 30d, or *replay* any past date):
  - Results arrive as a QoQ/YoY table of Revenue, EBITDA, PBT and PAT. Lenders get NII and asset quality.
  - A management change arrives with the incoming person's background and sources.
  - Deals and fund raises are sized against the company.
  - Routine paperwork is collapsed into one line.
  - Alerts fire on end-of-day moves and volume spikes against thresholds the user sets, with the ₹ impact on their position.
  - A 60-second spoken brief reads the top of the list.
- **Pull.** Research on any NSE ticker, grounded only in the company's own reported numbers, annual reports and concall transcripts:
  - Snapshot
  - **Promise vs delivered**: management's guidance from the last four calls scored against what was reported
  - Health check: trajectory, balance sheet, cash conversion
  - Bull vs bear
  - Every claim carries a tap-to-source citation, and follow-up questions are answered from the same documents.

## Key decisions and trade-offs

1. **Rules before models, models before reasoning models.**
   - 58% of filings are classified from their standardised BSE subject line with no LLM.
   - The rest go in batches of 15 to `gemini-3.5-flash-lite`.
   - Only promise-vs-delivered, bull/bear and Q&A use the stronger `gemini-3.6-flash`. I planned on 3.8-flash, but it was timing out on my key, so it's a one-variable switch with automatic fallback when a model is overloaded.
   - Every call is priced at Google's published rates in-app. **Everything built so far (110 filings classified, 3 executive bios, research dossiers for 23 companies) would cost $0.20 at paid rates.** The actual bill is ₹0 on the free tier.
   - Every response is cached in Postgres and logged; the app shows the routing and cache-hit rate.
   - A scheduler run with nothing new costs zero calls. The whole thing runs on free tiers.
2. **The model extracts; code judges.**
   - Materiality is computed from extracted facts sized against the company: order % of TTM revenue, raise % of market cap, rating direction, executive seniority.
   - The ranking is therefore deterministic and explainable. Each card's "why" chip is the actual computation.
3. **No generated number reaches the user unchecked.**
   - Results cards are computed, not written.
   - Filing text that disagrees with the reported table is flagged, not smoothed over (ITC: "19% revenue growth" vs 3.9%).
   - One-liners are rejected if any number in them isn't in the filing. This caught a real 10× crore/million slip.
   - Bios drop any organisation not present in their sources.
   - Research quotes are verified against the cited chunk.
4. **Promise vs delivered: the model reads, code keeps time.** Run on real transcripts (BEL, Titan, Asian Paints, KPIT), the first version failed in instructive ways:
   - Semantic search returned the transcript's cover page instead of management's outlook.
   - Half the genuine quotes were rejected because the PDF text layer breaks spacing ("15 %", "crore s").
   - The model scored FY27 guidance against FY26 numbers.
   
   Fixes:
   - A deterministic pre-filter picks forward-looking passages that contain numbers.
   - Quote checks ignore spacing but stay exact on every letter and digit.
   - **Whether a target period has been reported is computed, not generated.** A guard rejects any "actual" cited for a different period.
   - Segment claims are marked unverifiable rather than judged on company totals.
   - Unfinished periods get a year-to-date read: BEL's "15%+ revenue growth" is *tracking ahead* at +25%/+27% in H1, while KPIT's FY27 margin guide of 20.5–21.2% is *tracking behind* at ~15.5%.
5. **Primary sources only on the pull side**, as the brief asked. Web search is used for exactly one thing: the incoming executive's background on the push side.
6. **Data access, honestly.**
   - BSE's and NSE's APIs and PDF hosts refuse non-browser clients. I chose not to imitate a browser to get past that.
   - Screener.in became the filing index and the source of reported financials.
   - Annual reports and transcripts are uploaded, in-app or via a drop folder.
   - The trade-off: unseen tickers get numbers-based research instantly, and document-based sections once their PDFs are added.
7. **Built for the networks graders actually use.** Some Indian ISPs block `*.supabase.co` and render.com. The browser reaches Supabase only through the app's own domain (a server-side rewrite), so sign-in works on those networks. Research pages are pre-built after each refresh, so nobody waits on a cold model call. Uploads run as background jobs, and only saved accounts can change the shared document library.
8. **Guest-first auth.** "Try as guest" gets a seeded, fully working account in about 2 seconds with nothing to fill in. Row-level security isolates each user, and a guest can upgrade to email later.

## What I left out, deliberately

- Intraday data and news, outside the brief's spirit of filtering noise.
- Web push notifications: alerts live in an in-app inbox.
- Google sign-in, which is wired but off until OAuth credentials exist.
- Automated PDF retrieval from exchange hosts that block scripted clients.
- A broader research universe beyond on-demand fetching.

## Where I'd take it next

- Licensed exchange data feeds, removing the upload step, plus real-time filings via the exchanges' push products.
- Web push / WhatsApp delivery for the alerts users opt into.
- Learning the ranking from what each investor opens and dismisses.
- Guidance tracking across more quarters, with a "credibility score" per management team.
- Peer comparison inside research.
- An evaluation set for classification and promise extraction, so model or prompt changes can be measured rather than eyeballed.

## Links

- App: _(Vercel URL)_
- Repo: _(GitHub URL)_
- AI build history: _(Claude Code transcript export)_
