"""Polymarket odds collector — discovers all active GTA VI markets live."""
import requests
import pandas as pd
from datetime import date, timedelta
import re
import config

_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"
_GTA_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"GTA\s*(VI|6)", r"Grand Theft Auto\s*(VI|6)", r"Rockstar.*GTA", r"GTA.*launch",
]]


def _is_gta_market(title: str) -> bool:
    return any(p.search(title) for p in _GTA_PATTERNS)


def _discover_markets() -> list[dict]:
    """Query Gamma API for all active GTA VI related markets."""
    markets = []
    for keyword in ("GTA", "Grand Theft Auto"):
        params = {"q": keyword, "active": "true", "limit": 100, "offset": 0}
        while True:
            try:
                r = requests.get(f"{_GAMMA}/markets", params=params, timeout=30)
                r.raise_for_status()
                page = r.json()
            except Exception:
                break

            if not page:
                break

            for m in page:
                title = m.get("question", m.get("title", ""))
                if _is_gta_market(title):
                    markets.append(m)

            if len(page) < params["limit"]:
                break
            params["offset"] += params["limit"]

    # Deduplicate by conditionId
    seen = set()
    unique = []
    for m in markets:
        cid = m.get("conditionId", m.get("id", ""))
        if cid not in seen:
            seen.add(cid)
            unique.append(m)
    return unique


def _get_yes_token_id(market: dict) -> str | None:
    """Extract the Yes-outcome token ID from a market record."""
    tokens = market.get("tokens", [])
    for token in tokens:
        outcome = token.get("outcome", "").lower()
        if outcome == "yes":
            return token.get("token_id") or token.get("tokenId")
    # Fallback: first token if no outcome label
    if tokens:
        return tokens[0].get("token_id") or tokens[0].get("tokenId")
    return None


def _fetch_price_history(token_id: str, start: str) -> list[tuple[str, float]]:
    start_ts = int(
        pd.Timestamp(start).timestamp()
    )
    end_ts = int(pd.Timestamp(date.today().isoformat()).timestamp())
    params = {
        "market": token_id,
        "startTs": start_ts,
        "endTs": end_ts,
        "fidelity": 1440,  # 1-day buckets (minutes per bucket)
    }
    try:
        r = requests.get(f"{_CLOB}/prices-history", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    history = data.get("history", [])
    results = []
    for point in history:
        ts = point.get("t")
        price = point.get("p")
        if ts is not None and price is not None:
            obs = pd.Timestamp(ts, unit="s").strftime("%Y-%m-%d")
            results.append((obs, round(float(price), 6)))
    return results


def _slug_to_metric(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")[:48]


def collect(existing: pd.DataFrame) -> list[dict]:
    poly_rows = (
        existing[existing["source"] == "polymarket"]
        if not existing.empty
        else pd.DataFrame()
    )

    markets = _discover_markets()
    rows: list[dict] = []

    for market in markets:
        title = market.get("question", market.get("title", "unknown"))
        slug = market.get("slug", market.get("conditionId", "unknown"))
        metric = _slug_to_metric(slug)

        token_id = _get_yes_token_id(market)
        if not token_id:
            continue

        known = (
            poly_rows[poly_rows["metric"] == metric]["obs_date"].max()
            if not poly_rows.empty and metric in poly_rows["metric"].values
            else None
        )
        start = known if known else config.BACKFILL_START_DATE

        history = _fetch_price_history(token_id, start)
        for obs, prob in history:
            rows.append(
                {
                    "obs_date": obs,
                    "source": "polymarket",
                    "metric": metric,
                    "value": prob,
                    "unit": "prob",
                    "note": title[:120],
                }
            )

    return rows
