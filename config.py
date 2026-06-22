import os

TICKER = "TTWO"
ENTRY_PRICE = 250.0
LAUNCH_DATE = "2026-11-19"
BACKFILL_START_DATE = "2023-12-05"
TRAILER_DATES = ["2023-12-05"]

WIKI_ARTICLE = "Grand_Theft_Auto_VI"

YOUTUBE_VIDEO_IDS = ["EiQEBYDox_k"]
YOUTUBE_CHANNEL_HANDLE = "@RockstarGames"
YOUTUBE_CHANNEL_KEYWORDS = ["Grand Theft Auto VI", "GTA VI", "GTA 6"]
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# Empty → sources/polymarket.py discovers all active GTA VI markets live
POLYMARKET_SLUGS: list[str] = []

GDELT_QUERY = '("GTA VI" OR "GTA 6")'
GDELT_BROADEN = False
GDELT_ENGLISH_ONLY = True

STALE_DAYS = 10

HISTORY_CSV = "data/history.csv"
STATUS_JSON = "data/status.json"
DOCS_DIR = "docs"

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "ttwo-tracker contact@example.com")
