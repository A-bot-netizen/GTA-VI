# TTWO / GTA VI Hype Tracker — Build Spec

A handoff spec for **Claude Code**. Build a small Python project that collects a fixed set of
**clean, quantitative** metrics on the Take-Two (TTWO) / GTA VI pre-launch trade once a week,
stores them as a version-controlled time series, renders a static HTML dashboard with charts,
and publishes it to GitHub Pages via GitHub Actions. The owner shares the Pages link with a small
group of friends.

> The owner has deliberately chosen **no sentiment analysis, no NLP, no LLM calls**. Every metric
> below is a number pulled from an API. Do not add sentiment scoring, price-target scraping,
> Reddit, Stocktwits, Amazon/Best Buy, or Google Trends. See **Non-Goals**.

---

## 1. Goal & constraints

- **Cadence:** weekly (cron) + manual trigger.
- **Hosting:** runs entirely on GitHub Actions; publishes to GitHub Pages. No always-on PC needed
  (the chosen sources are robust API/open access and are not sensitive to the runner's datacenter IP).
- **Keys:** exactly **one** required — a free **YouTube Data API v3** key. Everything else uses open
  APIs (some require only a descriptive `User-Agent` header, not a credential).
- **Data store:** long-format CSV committed back to the repo, so git history *is* the time-series database.
- **Robustness:** each source isolated — one failing source must never abort the run or block the
  Pages deploy. Stale/failed sources must render a **visible** "last updated / unavailable" badge.
  A silently frozen line that everyone trusts is worse than a visibly broken one.

---

## 2. Architecture

```
collect.py  →  data/history.csv (+ data/status.json)  →  report.py  →  docs/index.html
     ▲                                                                        │
GitHub Actions (weekly cron + workflow_dispatch) ───────────────────► GitHub Pages (public link)
```

- `collect.py` runs each source module, upserts rows into `data/history.csv`, writes per-source
  status to `data/status.json`, and commits both back to the repo.
- `report.py` reads the CSV, builds Plotly charts, and writes a self-contained `docs/index.html`.
- The workflow runs both, commits data, and deploys `docs/` to Pages.

### Backfill vs forward-only (important)
Some sources expose full history and should be **backfilled** on first run and **idempotently
upserted** every run (dedupe on `source + metric + obs_date`). Others are point-in-time snapshots
that accumulate forward from first run. Build accordingly:

| Source | History available? | Behavior |
|---|---|---|
| Price (yfinance) | Yes (daily history) | Backfill + upsert daily closes |
| Wikipedia pageviews | Yes (daily since 2015) | Backfill + upsert daily |
| Polymarket odds | Yes (prices-history) | Backfill + upsert daily Yes-probability |
| GDELT volume | Yes (timeline API) | Backfill + upsert daily article volume |
| SEC Form 4 | Yes (all filings) | Backfill + upsert per filing date |
| YouTube views/likes | **No** (current totals only) | Snapshot each run; chart accumulates forward |
| Options P/C + IV | **No** (point-in-time) | Snapshot each run; accumulates forward |

---

## 3. Data schema — `data/history.csv`

Long format, one observation per row. Key on `(source, metric, obs_date)` for idempotent upserts.

| Column | Meaning |
|---|---|
| `obs_date` | Date the value pertains to (YYYY-MM-DD). For snapshot sources = run date. |
| `source` | `price` \| `youtube` \| `wikipedia` \| `polymarket` \| `gdelt` \| `sec` \| `options` |
| `metric` | e.g. `close`, `trailer3_views`, `pageviews`, `delay_yes_prob`, `insider_sale_usd`, `put_call_oi` |
| `value` | Numeric. |
| `unit` | `usd` \| `count` \| `prob` \| `ratio` \| `pct` |
| `note` | Optional free text (e.g. filing accession no., market slug). |

`data/status.json`: `{ source: { "last_success": ISO8601, "ok": bool, "error": str|null, "rows_written": int } }`.

---

## 4. Sources — exact build instructions

> Where it says **VERIFY AT BUILD TIME**, resolve the current value programmatically or check the
> live API rather than hardcoding — these are the parts most likely to have drifted.

### 4.1 Price — yfinance (open, no key)
- `yfinance.Ticker("TTWO")`. On first run pull daily history from `BACKFILL_START_DATE`
  (`.history(start=BACKFILL_START_DATE)`), store `close` per `obs_date`. Each run, upsert recent closes.
- Compute and store a derived `pct_vs_entry` metric using `ENTRY_PRICE` from config (~230).
- **Caveat:** yfinance is an unofficial Yahoo scraper; pin the version in `requirements.txt`,
  wrap in try/except, and record failure in status rather than crashing.

### 4.2 YouTube — Data API v3 (free key — OPTIONAL)
- **This is the only source needing an account, and it is optional.** If `YOUTUBE_API_KEY` is not set,
  `collect.py` must **skip this source cleanly** (no crash), and the dashboard renders everything else
  with a "YouTube — not configured" badge. This lets the owner do a first launch with zero accounts and
  add the key later. When the key is absent, mark the source `ok=true, skipped=true` in `status.json`
  (skipped ≠ failed — don't show a red error badge, show a neutral "not configured" one).
- Config holds a list of tracked GTA VI video IDs (the trailers). Owner pastes video IDs from the
  Rockstar Games channel as new trailers drop. Optionally also auto-discover by listing the channel's
  uploads playlist and filtering titles containing "Grand Theft Auto VI"/"Trailer".
- For each tracked video: `GET videos.list?part=statistics&id={id}&key={KEY}` → `viewCount`, `likeCount`.
- Store per video per run: `{id}_views`, `{id}_likes`, and derived `{id}_like_view_ratio`.
- **Dislikes are intentionally omitted** — YouTube removed the public dislike count in Dec 2021; the
  API returns 0 for videos you don't own, so any dislike ratio would be fabricated. Track views, likes,
  like/view ratio only.
- **VERIFY AT BUILD TIME:** the Rockstar channel ID / uploads playlist if using auto-discovery
  (resolve via `channels.list?forHandle=@RockstarGames`, don't hardcode).
- Quota is trivial (1 unit per `videos.list`; 10k/day limit).

### 4.3 Wikipedia pageviews — Wikimedia REST API (open, User-Agent only)
- Endpoint: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{ARTICLE}/daily/{start}/{end}`
- `ARTICLE` = the URL-encoded canonical title, expected `Grand_Theft_Auto_VI`. **VERIFY AT BUILD TIME**
  that this is the canonical article (follow redirects) before relying on it.
- Send a descriptive `User-Agent` header (e.g. `ttwo-tracker (owner-email)`). No key.
- Backfill the daily series **from `BACKFILL_START_DATE`** to today; upsert. Store `pageviews` per `obs_date`.

### 4.4 Polymarket — public read API (open, no key)
- Track the GTA VI markets the owner cares about: the **delay/"postponed again"** market (probability
  GTA VI does NOT release by 2026-11-19) and a **price-threshold** market (e.g. price > $70). Config
  holds market **slugs**.
- **VERIFY AT BUILD TIME:** Polymarket's API has changed before. Resolve each market by slug via the
  **Gamma API** (`https://gamma-api.polymarket.com/...`) to get the current condition/token IDs, then
  pull the "Yes" outcome token's **price history** (the CLOB prices-history endpoint, e.g.
  `https://clob.polymarket.com/prices-history?market={tokenId}&...`). The Yes-token price = implied
  probability. Do **not** hardcode token IDs from memory — discover them live.
- Backfill daily Yes-probability from `BACKFILL_START_DATE`; upsert. Store `delay_yes_prob`,
  `price_over_70_prob`, etc. (`unit=prob`). **Note:** these markets were created well after the trailer,
  so their lines will legitimately start later than `BACKFILL_START_DATE` (at market creation) — not a bug.
- Reading market data needs no auth (only trading does). Note in README that thin-volume markets are
  noisier — this is a display caveat, not a build concern.

### 4.5 SEC Form 4 (insider transactions) — EDGAR (open, User-Agent only)
- Resolve TTWO's CIK from `https://www.sec.gov/files/company_tickers.json` (ticker→CIK map).
  **Do not hardcode the CIK.**
- `GET https://data.sec.gov/submissions/CIK{cik:010d}.json` → recent filings; filter `form == "4"`.
- For each Form 4, fetch the ownership XML document and parse non-derivative transactions:
  `transactionShares`, `transactionPricePerShare`, `transactionCode` (S = open-market sale, etc.).
  Compute `shares * price` for sales.
- Where present, read the **10b5-1 plan flag** (newer Form 4s include an `aff10b5One`-style indicator /
  remarks) to split **plan vs discretionary** sales; if unavailable, store total and note it.
- Store per filing `obs_date`: `insider_sale_usd` (sum), `insider_filing_count`, and if available
  `insider_discretionary_usd`.
- Send a descriptive `User-Agent` (SEC fair-access requires it). Respect ~10 req/sec.
- **Caveat:** Form 4 XML is fiddly (multiple rows, derivative vs non-derivative). Handle both; primary
  metric is summed non-derivative sales.

### 4.6 GDELT — media coverage volume + tone (open, no key)
- Open DOC 2.0 API, no auth. Pull **two** timelines for the query:
  - Volume: `mode=timelinevolraw` (raw article counts) → store `media_volume` (`unit=count`).
  - Tone: `mode=timelinetone` (GDELT's precomputed average sentiment) → store `media_tone` (`unit=ratio`).
  - Base: `https://api.gdeltproject.org/api/v2/doc/doc?query={Q}&mode={MODE}&format=json` + date range.
    **VERIFY AT BUILD TIME** the current mode names and JSON shape.
- `Q` = config `GDELT_QUERY`, default `("GTA VI" OR "GTA 6")`. A `GDELT_BROADEN` flag (default **False**)
  appends `OR "Grand Theft Auto"`. **Leave broaden off by default:** it raises recall but drags in
  GTA V / GTA Online / general franchise coverage, contaminating the VI-launch signal. Only enable it
  if VI-specific volume proves too sparse. `GDELT_ENGLISH_ONLY` adds `sourcelang:english` to cut noise.
- Backfill both daily series **from `BACKFILL_START_DATE`** (GDELT DOC 2.0 covers 2017→present, so the
  Dec 2023 anchor is well within range); upsert.
- **Tone is a sentiment metric** (precomputed by GDELT — it adds no LLM calls to this pipeline). The
  owner has opted to include it; label it explicitly as "media sentiment (GDELT tone)" on the dashboard
  so it's never confused with the clean quantitative metrics. Typical GDELT tone runs roughly −10..+10
  (negative = adverse coverage); display the raw value and a smoothed line.
- **Caveat:** GDELT's source pool is broad and includes low-quality outlets; both lines are good for
  *trend shape*, not precise levels. Volume here is *press* attention — complementary to Wikipedia
  pageviews (reader attention), not redundant.

### 4.7 Options — yfinance (open, no key)
- `t = yfinance.Ticker("TTWO"); t.options` → expirations. Pick (a) the nearest expiry and (b) the
  expiry bracketing 2026-11-19. For each, `t.option_chain(exp)` → `calls`, `puts` with `openInterest`,
  `impliedVolatility`.
- Compute and store: `put_call_oi` = Σputs.openInterest / Σcalls.openInterest (`unit=ratio`), and a
  near-the-money average `iv_near` for the front expiry (`unit=pct`).
- Snapshot each run (no reliable free history). **Caveat:** Yahoo options data is occasionally
  patchy/delayed — guard against empty chains and division by zero.

---

## 5. Dashboard — `report.py` → `docs/index.html`

- Static, single file. Use **Plotly** with `include_plotlyjs="cdn"` (small page; loads Plotly from CDN).
- **Header block:** project title; global "Last updated: {run timestamp}"; current price + % vs entry;
  a **days-to-launch** countdown to 2026-11-19.
- **Charts** (each its own time-series panel, each with its own "source updated {date}" line, and a
  red **STALE** / **UNAVAILABLE** badge driven by `status.json` if a source is failed or older than a
  threshold, e.g. 10 days):
  1. Price ($) over time.
  2. Wikipedia pageviews (daily attention).
  3. YouTube — views per tracked trailer, and like/view ratio (the ratio is the engagement-quality
     line: holding up vs decaying as a trailer ages).
  4. Polymarket — Yes-probability lines (delay market + price-threshold market).
  5. Insider selling — $ per filing over time (bars), with plan vs discretionary split if available.
  6. Media coverage (GDELT) — daily article volume (press attention, distinct from Wikipedia reader
     attention) plus a clearly-labeled "media sentiment (GDELT tone)" line.
  7. Options — put/call OI ratio + near-term IV.
- **Trailer markers:** draw a faint vertical line + label on every time-series chart at each date in
  `TRAILER_DATES` (seeded with Trailer 1 = 2023-12-05), so spikes line up visibly with trailer drops.
- **Latest snapshot table:** every metric's most recent value + its date.
- **Auto-filled weekly summary:** generate a plain-text block matching the owner's existing
  "Weekly Update" format (price check, the week's clean signals, next key date = 2026-11-19) that
  friends can copy-paste. No commentary/recommendation text is generated — numbers only.

---

## 6. GitHub Actions — `.github/workflows/weekly.yml`

- Triggers: `schedule` (weekly cron, e.g. Monday 13:00 UTC) **and** `workflow_dispatch` (manual).
- `permissions: { contents: write, pages: write, id-token: write }`.
- Steps: checkout → setup-python → `pip install -r requirements.txt` →
  `python collect.py` (env: `YOUTUBE_API_KEY` from secret **if set — optional**; `SEC_USER_AGENT` from a
  repo variable) → commit `data/` back to the repo → `python report.py` →
  upload `docs/` as a Pages artifact (`actions/upload-pages-artifact`) → deploy (`actions/deploy-pages`).
- The data commit and Pages deploy must happen even if some sources failed or YouTube is unconfigured
  (partial success is normal — the dashboard should launch on the open sources alone).
- Pin action versions and `requirements.txt` versions for reproducibility.

---

## 7. Repo structure

```
ttwo-tracker/
  collect.py
  report.py
  config.py
  sources/
    price.py
    youtube.py
    wikipedia.py
    polymarket.py
    gdelt.py
    sec_form4.py
    options.py
  templates/dashboard.html.j2
  data/history.csv          # committed; the time-series DB
  data/status.json          # committed; per-source health
  docs/index.html           # generated; served by Pages
  requirements.txt
  .github/workflows/weekly.yml
  README.md
```

Suggested `config.py` values (confident defaults; resolve the marked ones live):
```python
TICKER = "TTWO"
ENTRY_PRICE = 230.0
LAUNCH_DATE = "2026-11-19"
BACKFILL_START_DATE = "2023-12-05"             # GTA VI Trailer 1 (released early on Dec 4 after a leak)
TRAILER_DATES = ["2023-12-05"]                 # owner appends later trailer dates; drawn as chart markers
WIKI_ARTICLE = "Grand_Theft_Auto_VI"          # VERIFY canonical title
YOUTUBE_VIDEO_IDS = []                          # owner pastes GTA VI trailer IDs (source is OPTIONAL)
POLYMARKET_SLUGS = ["gta-6-launch-postponed-again"]  # + a price market; VERIFY slugs live
GDELT_QUERY = '("GTA VI" OR "GTA 6")'           # media coverage volume + tone
GDELT_BROADEN = False                            # True appends OR "Grand Theft Auto" (lowers precision)
GDELT_ENGLISH_ONLY = True
STALE_DAYS = 10
# Secrets/vars (not in code): YOUTUBE_API_KEY (secret, OPTIONAL), SEC_USER_AGENT (variable, "ttwo-tracker email")
```

---

## 8. Build approach (do this in order)

1. Scaffold the repo + `requirements.txt` (`yfinance, pandas, requests, plotly, jinja2`).
2. Build `report.py` + template against **mock/sample `history.csv`** first, so the dashboard renders
   end-to-end before any live API is wired. Confirm charts + stale badges + weekly block work.
3. Implement sources one at a time, each independently runnable and individually testable. Start with
   the keyless/open ones (price, wikipedia, gdelt, sec, options, polymarket); do youtube last, and make
   it skip-on-missing-key so the first launch works with no accounts at all.
4. Wire `collect.py` to orchestrate with per-source try/except + `status.json`.
5. Add the workflow; test via `workflow_dispatch` (manual run) before trusting the cron.
6. Provide a `--dry-run`/sample mode that skips network and uses fixtures, for CI sanity and local dev.

---

## 9. Owner setup checklist (put in README)

**First launch — no accounts needed:**
1. Create a GitHub repo, push this project.
2. Add a repo **variable** `SEC_USER_AGENT` = `ttwo-tracker your-email@example.com` (just an identifying
   string, not a credential).
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions tab → run the workflow manually once (backfills history + verifies). Then the weekly cron runs it.
5. Share the Pages URL with friends. YouTube will show a neutral "not configured" badge — everything else
   is live.

**Add YouTube later (optional):**
6. Get a free **YouTube Data API v3** key: Google Cloud Console → enable "YouTube Data API v3" →
   create an API key. Add it as repo **secret** `YOUTUBE_API_KEY`.
7. Paste GTA VI trailer video IDs into `config.py` (`YOUTUBE_VIDEO_IDS`); add new ones as trailers drop.
   On the next run the YouTube charts start populating.

---

## 10. Non-goals (do not build)

- No sentiment **computation** in this pipeline and **no LLM/Anthropic API calls of any kind**. The one
  sentiment figure shown — GDELT tone — is precomputed by GDELT and merely displayed; we do not run any
  NLP or scoring ourselves.
- No analyst price-target tracking (owner cut this — it only exists via fragile scraping).
- No Reddit, Stocktwits, Amazon, Best Buy, or Google Trends.
- No trading or write actions against Polymarket — **read-only** market data.
- No user accounts, auth, or databases beyond the committed CSV. (YouTube key is optional, not required.)

## 11. Known fragilities (note in README, don't try to "fix")

- **yfinance** can break on Yahoo changes → pinned version + graceful failure + stale badge.
- **Polymarket** endpoints/slugs drift → always resolve by slug via Gamma at build/run time.
- **SEC Form 4** XML varies by filer → parse defensively; primary metric = summed non-derivative sales.
- **YouTube** only gives current totals → 24h/72h benchmarks can't be reconstructed retroactively;
  the chart builds forward from first run, and new trailer IDs must be added to config.
