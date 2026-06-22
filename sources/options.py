import yfinance as yf
import pandas as pd
from datetime import date
import config

_LAUNCH = date.fromisoformat(config.LAUNCH_DATE)


def _pick_expiries(expirations: tuple) -> list[str]:
    """Return the nearest expiry and the one bracketing the launch date."""
    today = date.today()
    exp_dates = []
    for e in expirations:
        try:
            exp_dates.append(date.fromisoformat(e))
        except ValueError:
            continue

    if not exp_dates:
        return []

    nearest = min(exp_dates, key=lambda d: abs((d - today).days))
    after_launch = [d for d in exp_dates if d >= _LAUNCH]
    bracket = min(after_launch, key=lambda d: (d - _LAUNCH).days) if after_launch else None

    picks = [nearest.isoformat()]
    if bracket and bracket != nearest:
        picks.append(bracket.isoformat())
    return picks


def collect(existing: pd.DataFrame) -> list[dict]:
    ticker = yf.Ticker(config.TICKER)
    expirations = ticker.options

    if not expirations:
        return []

    obs_date = date.today().isoformat()
    rows: list[dict] = []

    for exp in _pick_expiries(expirations):
        try:
            chain = ticker.option_chain(exp)
        except Exception:
            continue

        calls = chain.calls
        puts = chain.puts

        total_call_oi = int(calls["openInterest"].sum()) if not calls.empty else 0
        total_put_oi = int(puts["openInterest"].sum()) if not puts.empty else 0

        if total_call_oi > 0:
            pc_ratio = round(total_put_oi / total_call_oi, 4)
        else:
            pc_ratio = None

        # Near-the-money IV: options within 10% of current price
        try:
            current_price = ticker.fast_info.last_price
            atm_band = current_price * 0.10
            atm_calls = calls[abs(calls["strike"] - current_price) <= atm_band]
            iv_near = (
                round(float(atm_calls["impliedVolatility"].mean()) * 100, 2)
                if not atm_calls.empty
                else None
            )
        except Exception:
            iv_near = None

        label = "near" if exp == _pick_expiries(expirations)[0] else "launch_bracket"

        if pc_ratio is not None:
            rows.append(
                {
                    "obs_date": obs_date,
                    "source": "options",
                    "metric": f"put_call_oi_{label}",
                    "value": pc_ratio,
                    "unit": "ratio",
                    "note": f"exp={exp}",
                }
            )
        if iv_near is not None:
            rows.append(
                {
                    "obs_date": obs_date,
                    "source": "options",
                    "metric": f"iv_near_{label}",
                    "value": iv_near,
                    "unit": "pct",
                    "note": f"exp={exp} atm±10%",
                }
            )

    return rows
