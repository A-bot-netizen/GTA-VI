# TTWO / GTA VI Hype Tracker

A weekly-automated dashboard tracking quantitative signals on the Take-Two Interactive (TTWO) / GTA VI pre-launch trade. Runs entirely on GitHub Actions and publishes to GitHub Pages — no always-on server needed.

## Setup checklist

### First launch (no accounts needed)

1. Fork / clone this repo and push to GitHub.
2. **Pages source:** Settings → Pages → Source: **GitHub Actions**.
3. **SEC User-Agent** (required by SEC fair-access policy):
   Settings → Secrets and variables → Actions → **Variables** tab →
   Add variable `SEC_USER_AGENT` = `ttwo-tracker your-email@example.com`
4. Actions tab → select **Weekly TTWO Tracker** → **Run workflow** (manual trigger).
   This backfills all history and deploys the dashboard.
5. Share the Pages URL with friends. YouTube will show a neutral "not configured" badge — everything else is live.

### Add YouTube tracking (optional, free)

6. [Google Cloud Console](https://console.cloud.google.com/) → enable **YouTube Data API v3** → create an API key.
7. Settings → Secrets and variables → Actions → **Secrets** tab →
   Add secret `YOUTUBE_API_KEY` = your key.
8. Paste GTA VI trailer video IDs into `config.py` → `YOUTUBE_VIDEO_IDS`.
   New trailers from the Rockstar channel are also **auto-discovered** each run — you only need to seed the first one.

### Adding new trailer dates

When a new trailer drops, append its date to `TRAILER_DATES` in `config.py`:
```python
TRAILER_DATES = ["2023-12-05", "2025-04-XX"]  # add new dates here
```
All charts will draw a vertical marker at that date on the next run.

---

## Local development

```bash
# Install deps (requires uv: https://docs.astral.sh/uv/)
uv sync

# Dry-run: generates synthetic data, no API calls
uv run python collect.py --dry-run
uv run python report.py
# → open docs/index.html in a browser

# Run a single live source
uv run python collect.py --source price

# Full live collection
uv run python collect.py
uv run python report.py
```

---

## Architecture

```
collect.py  →  data/history.csv  +  data/status.json  →  report.py  →  docs/index.html
     ▲                                                                         │
GitHub Actions (weekly cron + workflow_dispatch) ──────────────────► GitHub Pages
```

| File | Purpose |
|---|---|
| `config.py` | All settings (entry price, dates, slugs, etc.) |
| `collect.py` | Orchestrator — runs each source, upserts CSV, writes status |
| `report.py` | Reads CSV + status, builds Plotly charts, renders dashboard |
| `templates/dashboard.html.j2` | Jinja2 HTML template |
| `sources/*.py` | One module per data source |
| `data/history.csv` | Long-format time-series (committed — git history = DB) |
| `data/status.json` | Per-source health (committed) |
| `docs/index.html` | Generated; served by Pages (not committed) |
| `.github/workflows/weekly.yml` | Monday 13:00 UTC + manual trigger |

## Data sources

| Source | Key needed? | Backfill? | Notes |
|---|---|---|---|
| Price (yfinance) | No | Yes, from 2023-12-05 | Daily TTWO closes |
| Wikipedia pageviews | No | Yes | Daily reader attention |
| GDELT media coverage | No | Yes | Press volume + precomputed tone |
| SEC Form 4 | No | Yes | Insider non-derivative sales |
| Polymarket | No | Yes | All active GTA VI markets, discovered live |
| Options (yfinance) | No | No (snapshot) | Put/call OI + near-ATM IV |
| YouTube | Yes (free) | No (snapshot) | Views, likes, channel stats; auto-discovers new trailers |

## Known fragilities (by design — not bugs)

- **yfinance** can break on Yahoo scraping changes → pinned version, graceful failure, stale badge
- **Polymarket** slugs and endpoints drift → slugs resolved live via Gamma API each run
- **SEC Form 4 XML** varies by filer → parsed defensively; primary metric = summed non-derivative sales
- **YouTube** only exposes current totals → charts build forward from first configured run; new trailer IDs auto-discovered from the Rockstar uploads playlist

## Config reference (`config.py`)

| Variable | Default | Meaning |
|---|---|---|
| `ENTRY_PRICE` | 250.0 | Your TTWO buy price — used for % vs entry metric |
| `LAUNCH_DATE` | 2026-11-19 | GTA VI launch date — countdown + options expiry bracket |
| `BACKFILL_START_DATE` | 2023-12-05 | Trailer 1 date — backfill anchor |
| `TRAILER_DATES` | ["2023-12-05"] | Vertical markers on all charts |
| `YOUTUBE_VIDEO_IDS` | ["EiQEBYDox_k"] | Seed video IDs; new trailers auto-discovered |
| `YOUTUBE_CHANNEL_HANDLE` | @RockstarGames | Channel for auto-discovery + channel stats |
| `STALE_DAYS` | 10 | Days since last success before a badge turns orange |
| `GDELT_BROADEN` | False | Set True to include "Grand Theft Auto" (lowers precision) |
| `GDELT_ENGLISH_ONLY` | True | Filters to English-language sources |
