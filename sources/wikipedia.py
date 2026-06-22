import time
import pandas as pd
from datetime import date, timedelta
import config
from ._retry import get_with_retry

_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
_HEADERS = {"User-Agent": config.SEC_USER_AGENT}
_INTER_CHUNK_PAUSE = 3  # seconds between chunk requests


def _fetch_range(article: str, start: str, end: str) -> list[dict]:
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    url = f"{_BASE}/en.wikipedia/all-access/user/{article}/daily/{start_fmt}/{end_fmt}"
    r = get_with_retry(url, headers=_HEADERS, timeout=30, base_delay=10, label="wikipedia")
    items = r.json().get("items", [])
    return [
        {
            "obs_date": item["timestamp"][:8],
            "source": "wikipedia",
            "metric": "pageviews",
            "value": int(item["views"]),
            "unit": "count",
            "note": article,
        }
        for item in items
    ]


def collect(existing: pd.DataFrame) -> list[dict]:
    article = config.WIKI_ARTICLE
    wiki_rows = (
        existing[existing["source"] == "wikipedia"]
        if not existing.empty
        else pd.DataFrame()
    )

    start = (
        config.BACKFILL_START_DATE
        if wiki_rows.empty
        else wiki_rows["obs_date"].max()
    )
    end = date.today().strftime("%Y-%m-%d")

    start_dt = date.fromisoformat(start)
    end_dt = date.fromisoformat(end)
    rows: list[dict] = []

    chunk_days = 490
    cursor = start_dt
    first = True
    while cursor <= end_dt:
        if not first:
            time.sleep(_INTER_CHUNK_PAUSE)
        first = False

        chunk_end = min(cursor + timedelta(days=chunk_days), end_dt)
        rows += _fetch_range(
            article,
            cursor.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d"),
        )
        cursor = chunk_end + timedelta(days=1)

    for r in rows:
        d = r["obs_date"]
        r["obs_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    return rows
