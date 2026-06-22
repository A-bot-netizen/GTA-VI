"""Polymarket odds collector — discovers all active GTA VI markets live."""
import time
import re
import pandas as pd
from datetime import date
import config
from ._retry import get_with_retry

_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"
_INTER_PAGE_PAUSE = 2   # seconds between Gamma pagination requests
_INTER_MARKET_PAUSE = 3  # seconds between CLOB price-history requests

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
        first_page = True
        while True:
            if not first_page:
                time.sleep(_INTER_PAGE_PAUSE)
            first_page = False

            try:
                r = get_with_retry(
                    f"{_GAMMA}/markets", params=params, timeout=30,
                    base_delay=15, label="polymarket/gamma",
                )
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

    seen: set[str] = set()
    unique = []
    for m in markets:
        cid = m.get("conditionId", m.get("id", ""))
        if cid not in seen:
            seen.add(cid)
            unique.append(m)
    return unique


def _get_yes_token_id(market: dict) -> str | None:
    tokens = market.get("tokens", [])
    for token in tokens:
        if token.get("outcome", "").lower() == "yes":
            return token.get("token_id") or token.get("tokenId")
    if tokens:
        return tokens[0].get("token_id") or tokens[0].get("tokenId")
    return None


def _fetch_price_history(token_id: str, start: str) -> list[tuple[str, float]]:
    params = {
        "market": token_id,
        "startTs": int(pd.Timestamp(start).timestamp()),
        "endTs": int(pd.Timestamp(date.today().isoformat()).timestamp()),
        "fidelity": 1440,
    }
    try:
        r = get_with_retry(
            f"{_CLOB}/prices-history", params=params, timeout=30,
            base_delay=15, label="polymarket/clob",
        )
        data = r.json()
    except Exception:
        return []

    results = []
    for point in data.get("history", []):
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

    for i, market in enumerate(markets):
        if i > 0:
            time.sleep(_INTER_MARKET_PAUSE)

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

        for obs, prob in _fetch_price_history(token_id, start):
            rows.append({
                "obs_date": obs,
                "source": "polymarket",
                "metric": metric,
                "value": prob,
                "unit": "prob",
                "note": title[:120],
            })

    return rows
