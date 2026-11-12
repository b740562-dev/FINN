# FINN: submission write-up (draft for the covering email)

## What I built

FINN is a mobile-first PWA for an investor holding a portfolio of NSE stocks. It has one opinion about interaction: **the investor's scarce resource is attention, so the home screen shows what changed as pictures and numbers, and every item has to justify its place.** Text is one tap away, never the first thing you see.

- **Push (Today + Alerts).** A ranked digest for any window (24h / 7d / 30d, or *replay* any past date):
  - **Top news** opens with a row of story bubbles for the six most important items, then one row per update showing an icon, the ticker and its signal, with no sentences:
    - results: `Rev ▲12% · PAT ▲16%`, with a ⚑ if the filing disagrees with the reported table;
    - a management change: portraits of the person leaving (or retiring) → the person joining;
    - a deal or fund raise: `₹4,265 cr · 4.3% mcap · QIP`;
    - a rating change: `↗ Outlook +`.
  - Tapping any item opens the full story: the Revenue / EBITDA / PBT / PAT table (QoQ and YoY; lenders get NII and asset quality), the incoming executive's background with sources, and why it ranks where it does.
  - Routine filings fold into one line, colour-coded *Worth a look / Minor / Paperwork*.
  - Alerts fire on end-of-day moves and volume spikes against thresholds the user sets, with the ₹ impact on their position. They're colour-coded by kind: drops red, jumps green, volume spikes amber, filings by importance. A search bar checks **any** NSE company for important filings, before you buy it.
  - When a company publishes a new concall, presentation or annual report, holders are told once FINN has read it ("Reliance Annual Report FY26 is out. FINN read it and updated the research.").
  - A 60-second spoken brief reads the top of the list.
- **Pull (Research).** Research on any NSE ticker, grounded only in the company's own reported numbers, annual reports and concall transcripts:
  - Snapshot
  - **Promise vs delivered**: management's guidance from the last four calls scored against what was reported
  - Health check: trajectory, balance sheet, cash conversion
  - Bull vs bear, as headline stats rather than paragraphs
  - Every claim carries a tap-to-source citation.
  - The Research tab ranks what deserves a look:
    - **top research picks**: companies with full documents loaded;
    - **your holdings**, each tagged *Important* (a material filing in the last 14 days), *Volatile* (20-day volatility ≥ 35% a year), *Promising* (price up over 3 months with profit up > 10% YoY) or *Steady*, with the numbers behind the tag;
    - **Worth checking**: the rest of the market, ranked by what changed, with a one-line reason built from the data.
  - **New reports**: what FINN has read on its own this week, and what is waiting to be added (see decision 8).
- **Ask Surya.** A round *Ask me* button on every screen opens a chat with an investment guide. You can type, or **speak** (transcribed on the server).
  - General guidance (how to judge debt, when to rebalance) is answered freely.
  - **Anything about a specific company's data comes only from verified material.** An answer with figures that pass the checks shows a green **✓ Verified** line, linking each source to the original (the exchange PDF opened at the cited page, or the company's reported financials).
  - When the material doesn't exist, Surya says so. If a newer report is out but not yet read, it names it ("SBIN's Q2 FY27 concall is out…") and offers a one-tap, pre-filled upload.
  - Logged-in users keep their **chat history** across devices. Any conversation **exports** to PDF or Markdown with its sources. Every new login starts with a fresh chat.
- **You.** Portfolio (defaults to India's seven largest listed companies; **Reset** zeroes the quantities but keeps the companies), alert sensitivity, *Your documents* (add an annual report, concall or presentation, record where it came from, remove it later), and a profile. Guests get a working account in one tap; **logging in uses a 6-digit email code**, keeps the guest's portfolio, and shows a verified ✓.

## Key decisions and trade-offs

1. **Rules before models, models before reasoning models.**
   - 57% of filings (119 of 208) are classified from their standardised BSE subject line with no LLM.
   - The rest go in batches of 15 to `gemini-3.5-flash-lite`, which also transcribes voice questions.
   - Only promise-vs-delivered, bull/bear and Surya's answers use the stronger `gemini-3.6-flash`. I planned on 3.8-flash, but it was timing out on my key, so it's a one-variable switch with automatic fallback when a model is overloaded.
   - Every call is priced at Google's published rates. **Everything built so far would cost $1.04 at paid rates:** 208 filings classified, 8 executive bios, research for 36 companies, 33 documents indexed, and 50 Surya replies (19 of them repeats served from the cache). The actual bill is ₹0 on the free tier.
   - Every response is cached in Postgres and logged. A scheduler run with nothing new costs zero calls. The cost and routing meter is **admin-only**: the API returns 403 and strips model names for everyone else.
2. **The model extracts; code judges.**
   - Materiality is computed from extracted facts sized against the company: order % of TTM revenue, raise % of market cap, rating direction, executive seniority.
   - The ranking is therefore deterministic and explainable. Each item's "why" is the actual computation.
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
5. **Surya: free to advise, strict about facts.** The rule I set for the chat ("general advice is fine, data only from verified documents") is enforced in code, not just asked of the model:
   - Companies are detected deterministically (symbol, name, or a first word no other company shares), so "Adani Green" is never mistaken for Adani Enterprises.
   - "Verified material" means the company's own documents, its exchange-reported financials, and the Promise vs Delivered tracker. Each fact carries a marker.
   - Every quote must occur in the passage it cites, unknown markers are stripped, and **every number in a company answer must appear in the material it cites**. Otherwise the answer is replaced with "I don't have that in a verified document yet; add the matching report".
   - Testing on real documents surfaced the same failure modes as before, now fixed:
     - exchange cover letters outranked real content on vague questions, so retrieval strips the company name and filters boilerplate;
     - the PDF wrote "72 , 000 crores", so numbers are rejoined before checking;
     - "[c2, c4]" citations hid stray digits, so combined markers are split and checked one by one.
   - Results: *BEL's order book* → ₹73,882 cr, ✓ Verified, linking to the annual report PDF at p.63. *HDFC Bank's NIM guidance* → "I don't have that yet, add the latest concall".
6. **Primary sources only on the pull side**, as the brief asked. Web search is used for exactly one thing: the incoming executive's background on the push side.
7. **Data access, honestly.**
   - BSE's and NSE's APIs and PDF hosts refuse non-browser clients. I chose not to imitate a browser to get past that.
   - Screener.in became the filing index and the source of reported financials. Any company is loaded on first search, and filings and numbers refresh on their own every two hours.
   - The trade-off: unseen tickers get numbers-based research instantly, and document-based sections once their PDFs are in.
8. **New reports: automatic where the source allows, a person where it doesn't.**
   - Every scheduler run records each company's newly published concall transcripts, presentations and annual reports.
   - FINN downloads each one with its honest, self-identifying client: directly when the host allows, or from the company's own investor-relations site when the listed link is on BSE. It then indexes the report, rebuilds the research and alerts holders.
   - First run: of 62 new reports, **13 were read with no human involved** (6 direct, 7 found on company websites: Reliance's and ICICI Bank's annual reports, HDFC Bank's Q2 concall and more).
   - **The rest need a person.** BSE refused all 90 of 90 links I tested, so for BSE-only reports someone must open the original, **download the PDF and add it**. The app makes this as light as possible: the report is listed under Research → New reports and inside Surya with every field pre-filled, so it's one download and one tap, and any logged-in user can do it. Uploads feed a shared library, so guests can't, and an uploader can remove what they added.
   - **On a paid tier this needs no human at all.** A licensed exchange data product (BSE/NSE) or a vendor feed delivers filings and documents through an authorised API, and the same pipeline would index them the moment they're published.
9. **Built for the networks graders actually use.** Some Indian ISPs block `*.supabase.co` and render.com. The browser reaches Supabase only through the app's own domain (a server-side rewrite), so sign-in works on those networks. Research pages are pre-built after each refresh, so nobody waits on a cold model call, and uploads run as background jobs.
10. **Guest-first, then a code.** "Try as guest" gets a seeded, fully working account in about 2 seconds with nothing to fill in. Logging in later is a 6-digit email code rather than a magic link (no tab switching on a phone). For a guest, the email is attached to the same account, so their portfolio, alerts and settings come along. Row-level security isolates every user.

## What I left out, deliberately

- Intraday data and news, outside the brief's spirit of filtering noise.
- Web push notifications: alerts live in an in-app inbox.
- Google sign-in, which is wired but off until OAuth credentials exist.
- Imitating a browser to download from exchange hosts that block scripted clients. BSE-only reports are added by a person until a licensed feed replaces that step.
- Buy/sell calls. Surya helps the user think about a decision but never gives a recommendation or price target.

## Where I'd take it next

- A licensed exchange or vendor data feed (paid tier): every report ingested with no human step, plus real-time filings via the exchanges' push products.
- Web push / WhatsApp delivery for the alerts users opt into.
- Learning the ranking from what each investor opens and dismisses.
- Guidance tracking across more quarters, with a "credibility score" per management team.
- Peer comparison inside research, and in Surya ("compare HDFC Bank and ICICI Bank's asset quality").
- An evaluation set for classification, promise extraction and Surya's grounding, so model or prompt changes can be measured rather than eyeballed.

## Links

- App: _(Vercel URL)_
- Repo: https://github.com/b740562-dev/FINN
- AI build history: _(Claude Code transcript export)_
