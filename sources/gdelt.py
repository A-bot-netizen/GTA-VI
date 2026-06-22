import time
import pandas as pd
from datetime import date
import config
from ._retry import get_with_retry

_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_INTER_MODE_PAUSE = 15  # seconds between volume and tone requests


def _build_query() -> str:
    q = config.GDELT_QUERY
    if config.GDELT_BROADEN:
        q = q.rstrip(")") + ' OR "Grand Theft Auto")'
    if config.GDELT_ENGLISH_ONLY:
        q += " sourcelang:english"
    return q


def _fetch_timeline(mode: str, start: str, end: str) -> list[tuple[str, float]]:
    """Returns list of (YYYY-MM-DD, value). Retries via shared helper."""
    params = {
        "query": _build_query(),
        "mode": mode,
        "format": "json",
        "startdatetime": start.replace("-", "") + "000000",
        "enddatetime": end.replace("-", "") + "235959",
        "timelinesmooth": 0,
    }
    r = get_with_retry(
        _BASE, params=params, timeout=90, base_delay=30, label=f"gdelt/{mode}"
    )
    data = r.json()
    timeline = data.get("timeline", [])
    if not timeline:
        return []
    results = []
    for p in timeline[0].get("data", []):
        raw = p.get("date", "")
        if len(raw) >= 8:
            obs = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            results.append((obs, float(p.get("value", 0))))
    return results


def collect(existing: pd.DataFrame) -> list[dict]:
    gdelt_rows = (
        existing[existing["source"] == "gdelt"]
        if not existing.empty
        else pd.DataFrame()
    )

    start = (
        config.BACKFILL_START_DATE
        if gdelt_rows.empty
        else gdelt_rows["obs_date"].max()
    )
    end = date.today().strftime("%Y-%m-%d")

    rows: list[dict] = []

    vol_points = _fetch_timeline("timelinevolraw", start, end)
    for obs, val in vol_points:
        rows.append({
            "obs_date": obs,
            "source": "gdelt",
            "metric": "media_volume",
            "value": val,
            "unit": "count",
            "note": "GDELT DOC 2.0 raw article count",
        })

    time.sleep(_INTER_MODE_PAUSE)

    tone_points = _fetch_timeline("timelinetone", start, end)
    for obs, val in tone_points:
        rows.append({
            "obs_date": obs,
            "source": "gdelt",
            "metric": "media_tone",
            "value": round(val, 4),
            "unit": "ratio",
            "note": "GDELT precomputed average tone (~-10..+10)",
        })

    return rows
