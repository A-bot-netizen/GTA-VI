import requests
import pandas as pd
from datetime import date, timedelta
import config

_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


def _build_query() -> str:
    q = config.GDELT_QUERY
    if config.GDELT_BROADEN:
        q = q.rstrip(")") + ' OR "Grand Theft Auto")'
    if config.GDELT_ENGLISH_ONLY:
        q += " sourcelang:english"
    return q


def _fetch_timeline(mode: str, start: str, end: str) -> list[tuple[str, float]]:
    """Returns list of (YYYY-MM-DD, value) for the given mode."""
    start_fmt = start.replace("-", "") + "000000"
    end_fmt = end.replace("-", "") + "235959"
    params = {
        "query": _build_query(),
        "mode": mode,
        "format": "json",
        "startdatetime": start_fmt,
        "enddatetime": end_fmt,
        "timelinesmooth": 0,
    }
    r = requests.get(_BASE, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    # GDELT timeline JSON: {"timeline": [{"data": [{"date": "...", "value": N}, ...]}]}
    timeline = data.get("timeline", [])
    if not timeline:
        return []
    points = timeline[0].get("data", [])
    results = []
    for p in points:
        raw_date = p.get("date", "")
        # GDELT returns dates like "20231205000000"
        if len(raw_date) >= 8:
            obs = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
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
        rows.append(
            {
                "obs_date": obs,
                "source": "gdelt",
                "metric": "media_volume",
                "value": val,
                "unit": "count",
                "note": "GDELT DOC 2.0 raw article count",
            }
        )

    tone_points = _fetch_timeline("timelinetone", start, end)
    for obs, val in tone_points:
        rows.append(
            {
                "obs_date": obs,
                "source": "gdelt",
                "metric": "media_tone",
                "value": round(val, 4),
                "unit": "ratio",
                "note": "GDELT precomputed average tone (~-10..+10)",
            }
        )

    return rows
