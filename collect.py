#!/usr/bin/env python3
"""Collect all TTWO/GTA VI data sources and upsert into data/history.csv."""
import argparse
import importlib
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import config

SCHEMA = ["obs_date", "source", "metric", "value", "unit", "note"]

SOURCE_MAP = {
    "price": "sources.price",
    "wikipedia": "sources.wikipedia",
    "gdelt": "sources.gdelt",
    "sec": "sources.sec_form4",
    "options": "sources.options",
    "polymarket": "sources.polymarket",
    "youtube": "sources.youtube",
}


def load_existing() -> pd.DataFrame:
    p = Path(config.HISTORY_CSV)
    if p.exists() and p.stat().st_size > 1:
        return pd.read_csv(p, dtype={"obs_date": str, "note": str}).fillna("")
    return pd.DataFrame(columns=SCHEMA)


def upsert(existing: pd.DataFrame, new_rows: list[dict]) -> tuple[pd.DataFrame, int]:
    if not new_rows:
        return existing, 0
    new_df = pd.DataFrame(new_rows, columns=SCHEMA).fillna("")
    combined = pd.concat([existing, new_df], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["source", "metric", "obs_date"], keep="last"
    )
    combined = combined.sort_values(["obs_date", "source", "metric"]).reset_index(drop=True)
    added = len(combined) - len(existing)
    return combined, max(added, 0)


def save_history(df: pd.DataFrame) -> None:
    Path(config.HISTORY_CSV).parent.mkdir(exist_ok=True)
    df.to_csv(config.HISTORY_CSV, index=False)


def load_status() -> dict:
    p = Path(config.STATUS_JSON)
    if p.exists() and p.stat().st_size > 2:
        with open(p) as f:
            return json.load(f)
    return {}


def save_status(status: dict) -> None:
    Path(config.STATUS_JSON).write_text(json.dumps(status, indent=2))


def _run_source(name: str, module, existing: pd.DataFrame) -> tuple[list[dict], dict]:
    """Normalize source return: always returns (rows, extra_status)."""
    if name == "youtube":
        result = module.collect(existing)
        return result if isinstance(result, tuple) else (result, {})
    return module.collect(existing), {}


def _sample_rows() -> list[dict]:
    """Synthetic data for --dry-run. Deterministic, no network calls."""
    rng = random.Random(42)
    rows: list[dict] = []
    start = date.fromisoformat(config.BACKFILL_START_DATE)
    today = date.today()

    day, price = start, 180.0
    while day <= today:
        ds = day.isoformat()
        price = max(50.0, price + rng.uniform(-3, 3.5))
        pct = round((price - config.ENTRY_PRICE) / config.ENTRY_PRICE * 100, 4)
        rows += [
            {"obs_date": ds, "source": "price", "metric": "close", "value": round(price, 2), "unit": "usd", "note": ""},
            {"obs_date": ds, "source": "price", "metric": "pct_vs_entry", "value": pct, "unit": "pct", "note": f"entry={config.ENTRY_PRICE}"},
            {"obs_date": ds, "source": "wikipedia", "metric": "pageviews", "value": rng.randint(5_000, 80_000), "unit": "count", "note": "Grand_Theft_Auto_VI"},
            {"obs_date": ds, "source": "gdelt", "metric": "media_volume", "value": rng.randint(20, 300), "unit": "count", "note": ""},
            {"obs_date": ds, "source": "gdelt", "metric": "media_tone", "value": round(rng.uniform(-4, 4), 2), "unit": "ratio", "note": ""},
        ]
        day += timedelta(days=1)

    # YouTube — weekly snapshots forward from backfill start
    snap, views = start, 100_000_000
    while snap <= today:
        ds = snap.isoformat()
        views = int(views * rng.uniform(1.0, 1.02))
        likes = int(views * rng.uniform(0.03, 0.05))
        for vid in config.YOUTUBE_VIDEO_IDS:
            rows += [
                {"obs_date": ds, "source": "youtube", "metric": f"{vid}_views", "value": views, "unit": "count", "note": "GTA VI Trailer 1 (sample)"},
                {"obs_date": ds, "source": "youtube", "metric": f"{vid}_likes", "value": likes, "unit": "count", "note": "GTA VI Trailer 1 (sample)"},
                {"obs_date": ds, "source": "youtube", "metric": f"{vid}_like_view_ratio", "value": round(likes / views, 6), "unit": "ratio", "note": "GTA VI Trailer 1 (sample)"},
            ]
        rows += [
            {"obs_date": ds, "source": "youtube", "metric": "channel_views", "value": 85_000_000 + rng.randint(0, 100_000), "unit": "count", "note": "@RockstarGames"},
            {"obs_date": ds, "source": "youtube", "metric": "channel_subs", "value": 18_000_000 + rng.randint(0, 5_000), "unit": "count", "note": "@RockstarGames"},
        ]
        snap += timedelta(days=7)

    # Polymarket — market created ~Mar 2024, probability trends down toward launch
    poly_start = date(2024, 3, 1)
    prob = 0.28
    day = poly_start
    while day <= today:
        ds = day.isoformat()
        prob = max(0.02, min(0.95, prob + rng.uniform(-0.015, 0.008)))
        rows.append({"obs_date": ds, "source": "polymarket", "metric": "gta_6_postponed_again", "value": round(prob, 4), "unit": "prob", "note": "Will GTA VI be delayed past 2026? (sample)"})
        day += timedelta(days=1)

    # SEC — sparse filings
    for offset in [90, 210, 400, 620]:
        fd = (start + timedelta(days=offset))
        if fd > today:
            continue
        usd = rng.randint(500_000, 5_000_000)
        rows += [
            {"obs_date": fd.isoformat(), "source": "sec", "metric": "insider_sale_usd", "value": usd, "unit": "usd", "note": "sample-0000001"},
            {"obs_date": fd.isoformat(), "source": "sec", "metric": "insider_filing_count", "value": 2, "unit": "count", "note": "sample-0000001"},
            {"obs_date": fd.isoformat(), "source": "sec", "metric": "insider_discretionary_usd", "value": round(usd * rng.uniform(0.4, 0.7), 2), "unit": "usd", "note": "sample-0000001"},
        ]

    # Options — weekly snapshots (last 90 days)
    opt_day = today - timedelta(days=90)
    while opt_day <= today:
        ds = opt_day.isoformat()
        rows += [
            {"obs_date": ds, "source": "options", "metric": "put_call_oi_near", "value": round(rng.uniform(0.6, 1.4), 4), "unit": "ratio", "note": "exp=sample"},
            {"obs_date": ds, "source": "options", "metric": "iv_near_near", "value": round(rng.uniform(25, 55), 2), "unit": "pct", "note": "exp=sample atm±10%"},
        ]
        opt_day += timedelta(days=7)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect TTWO/GTA VI tracker data")
    parser.add_argument(
        "--dry-run", "--sample", action="store_true",
        help="Generate synthetic sample data — no network calls",
    )
    parser.add_argument(
        "--source", metavar="NAME",
        help="Run only one source (price | wikipedia | gdelt | sec | options | polymarket | youtube)",
    )
    args = parser.parse_args()

    existing = load_existing()
    status = load_status()
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    if args.dry_run:
        print("[dry-run] Generating synthetic sample data — no network calls")
        rows = _sample_rows()
        df, n = upsert(existing, rows)
        save_history(df)
        for src in SOURCE_MAP:
            status[src] = {"last_success": now_iso, "ok": True, "error": None, "rows_written": n}
        save_status(status)
        print(f"[dry-run] Done — {n} rows upserted into {config.HISTORY_CSV}")
        return

    targets = [args.source] if args.source else list(SOURCE_MAP.keys())

    for src_name in targets:
        if src_name not in SOURCE_MAP:
            print(f"[warn] Unknown source '{src_name}' — skipped", file=sys.stderr)
            continue

        module = importlib.import_module(SOURCE_MAP[src_name])
        print(f"[{src_name}] Collecting…", flush=True)
        try:
            rows, extra = _run_source(src_name, module, existing)

            if extra.get("skipped"):
                status[src_name] = {
                    "last_success": status.get(src_name, {}).get("last_success"),
                    "ok": True,
                    "error": None,
                    "rows_written": 0,
                    "skipped": True,
                    "skip_reason": extra.get("skip_reason", ""),
                }
                print(f"[{src_name}] Skipped — {extra.get('skip_reason', '')}")
                continue

            existing, n = upsert(existing, rows)
            save_history(existing)
            status[src_name] = {
                "last_success": now_iso,
                "ok": True,
                "error": None,
                "rows_written": n,
            }
            print(f"[{src_name}] Done — {n} new rows")

        except Exception as exc:
            status[src_name] = {
                "last_success": status.get(src_name, {}).get("last_success"),
                "ok": False,
                "error": str(exc),
                "rows_written": 0,
            }
            print(f"[{src_name}] ERROR: {exc}", file=sys.stderr)

    save_status(status)
    print("Collection complete.")


if __name__ == "__main__":
    main()
