"""YouTube Data API v3 collector. Skips cleanly if YOUTUBE_API_KEY is not set."""
import requests
import pandas as pd
from datetime import date
import config

_BASE = "https://www.googleapis.com/youtube/v3"
_SKIP_RESULT = {"ok": True, "skipped": True, "skip_reason": "YOUTUBE_API_KEY not configured"}


def _get_channel_id(handle: str, key: str) -> str | None:
    """Resolve a channel handle (@RockstarGames) to a channel ID."""
    handle_clean = handle.lstrip("@")
    r = requests.get(
        f"{_BASE}/channels",
        params={"part": "id", "forHandle": handle_clean, "key": key},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0]["id"] if items else None


def _get_uploads_playlist(channel_id: str, key: str) -> str | None:
    r = requests.get(
        f"{_BASE}/channels",
        params={"part": "contentDetails", "id": channel_id, "key": key},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _discover_video_ids(playlist_id: str, key: str) -> list[str]:
    """List up to 200 recent uploads, filter by GTA VI keywords."""
    ids: list[str] = []
    page_token = None
    keywords = [kw.lower() for kw in config.YOUTUBE_CHANNEL_KEYWORDS]

    while len(ids) < 200:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": key,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get(f"{_BASE}/playlistItems", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for item in data.get("items", []):
            title = item["snippet"].get("title", "").lower()
            if any(kw in title for kw in keywords):
                vid_id = item["snippet"]["resourceId"]["videoId"]
                if vid_id not in ids:
                    ids.append(vid_id)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return ids


def _get_video_stats(video_ids: list[str], key: str) -> dict[str, dict]:
    """Fetch statistics for up to 50 video IDs at once."""
    stats: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        r = requests.get(
            f"{_BASE}/videos",
            params={"part": "statistics,snippet", "id": ",".join(batch), "key": key},
            timeout=30,
        )
        r.raise_for_status()
        for item in r.json().get("items", []):
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "title": item["snippet"].get("title", ""),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
            }
    return stats


def _get_channel_stats(channel_id: str, key: str) -> dict:
    r = requests.get(
        f"{_BASE}/channels",
        params={"part": "statistics", "id": channel_id, "key": key},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return {}
    return items[0].get("statistics", {})


def collect(existing: pd.DataFrame) -> tuple[list[dict], dict]:
    """Returns (rows, status_extra). status_extra may contain skipped=True."""
    key = config.YOUTUBE_API_KEY
    if not key:
        return [], _SKIP_RESULT

    obs_date = date.today().isoformat()
    rows: list[dict] = []

    channel_id = _get_channel_id(config.YOUTUBE_CHANNEL_HANDLE, key)
    if not channel_id:
        raise ValueError(f"Could not resolve channel: {config.YOUTUBE_CHANNEL_HANDLE}")

    playlist_id = _get_uploads_playlist(channel_id, key)
    discovered_ids: list[str] = []
    if playlist_id:
        discovered_ids = _discover_video_ids(playlist_id, key)

    # Union of seeded + discovered IDs
    all_ids = list(dict.fromkeys(config.YOUTUBE_VIDEO_IDS + discovered_ids))

    video_stats = _get_video_stats(all_ids, key)
    for vid_id, s in video_stats.items():
        views = s["views"]
        likes = s["likes"]
        ratio = round(likes / views, 6) if views > 0 else 0.0
        title_note = s["title"][:80]

        rows += [
            {
                "obs_date": obs_date,
                "source": "youtube",
                "metric": f"{vid_id}_views",
                "value": views,
                "unit": "count",
                "note": title_note,
            },
            {
                "obs_date": obs_date,
                "source": "youtube",
                "metric": f"{vid_id}_likes",
                "value": likes,
                "unit": "count",
                "note": title_note,
            },
            {
                "obs_date": obs_date,
                "source": "youtube",
                "metric": f"{vid_id}_like_view_ratio",
                "value": ratio,
                "unit": "ratio",
                "note": title_note,
            },
        ]

    # Channel-level stats
    ch_stats = _get_channel_stats(channel_id, key)
    if ch_stats:
        rows += [
            {
                "obs_date": obs_date,
                "source": "youtube",
                "metric": "channel_views",
                "value": int(ch_stats.get("viewCount", 0)),
                "unit": "count",
                "note": config.YOUTUBE_CHANNEL_HANDLE,
            },
            {
                "obs_date": obs_date,
                "source": "youtube",
                "metric": "channel_subs",
                "value": int(ch_stats.get("subscriberCount", 0)),
                "unit": "count",
                "note": config.YOUTUBE_CHANNEL_HANDLE,
            },
        ]

    return rows, {}
