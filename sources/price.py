import yfinance as yf
import pandas as pd
import config


def collect(existing: pd.DataFrame) -> list[dict]:
    ticker = yf.Ticker(config.TICKER)

    price_rows = (
        existing[existing["source"] == "price"]
        if not existing.empty
        else pd.DataFrame()
    )

    if price_rows.empty:
        hist = ticker.history(start=config.BACKFILL_START_DATE)
    else:
        last = price_rows["obs_date"].max()
        hist = ticker.history(start=last)

    if hist.empty:
        return []

    rows = []
    for dt, row in hist.iterrows():
        obs_date = dt.strftime("%Y-%m-%d")
        close = round(float(row["Close"]), 4)
        pct = round((close - config.ENTRY_PRICE) / config.ENTRY_PRICE * 100, 4)
        rows += [
            {
                "obs_date": obs_date,
                "source": "price",
                "metric": "close",
                "value": close,
                "unit": "usd",
                "note": "",
            },
            {
                "obs_date": obs_date,
                "source": "price",
                "metric": "pct_vs_entry",
                "value": pct,
                "unit": "pct",
                "note": f"entry={config.ENTRY_PRICE}",
            },
        ]

    return rows
