#!/usr/bin/env python3
"""Generate the TTWO/GTA VI static dashboard → docs/index.html."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

import config

_LAYOUT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=60, r=24, t=28, b=40),
    height=320,
    legend=dict(orientation="h", y=-0.18, font=dict(size=10)),
    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", type="date"),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
    font=dict(family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", size=11),
    hovermode="x unified",
)

_TRAILER_COLOR = "rgba(251,191,36,0.4)"


def _add_trailers(fig: go.Figure) -> None:
    for i, td in enumerate(config.TRAILER_DATES, 1):
        fig.add_shape(
            type="line", x0=td, x1=td, y0=0, y1=1, yref="paper",
            line=dict(color=_TRAILER_COLOR, dash="dash", width=1),
        )
        fig.add_annotation(
            x=td, y=0.97, yref="paper", text=f"T{i}", showarrow=False,
            font=dict(size=9, color=_TRAILER_COLOR), textangle=-90,
        )


def _empty_fig(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**_LAYOUT_BASE)
    fig.add_annotation(
        text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=13, color="#475569"),
    )
    return fig


def _div(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


# ---- Chart builders ----

def _price_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "price"]
    if src.empty:
        return _empty_fig("Price data not yet collected")

    close = src[src["metric"] == "close"].sort_values("obs_date")
    pct = src[src["metric"] == "pct_vs_entry"].sort_values("obs_date")
    fig = go.Figure()

    if not close.empty:
        fig.add_trace(go.Scatter(
            x=close["obs_date"], y=close["value"].astype(float),
            name="TTWO Close ($)", mode="lines",
            line=dict(color="#60a5fa", width=2),
        ))
        fig.add_hline(
            y=config.ENTRY_PRICE, line_dash="dot",
            line_color="rgba(251,191,36,0.5)",
            annotation_text=f"Entry ${config.ENTRY_PRICE:.0f}",
            annotation_position="bottom right",
            annotation_font_color="rgba(251,191,36,0.7)",
        )

    if not pct.empty:
        fig.add_trace(go.Scatter(
            x=pct["obs_date"], y=pct["value"].astype(float),
            name="% vs Entry", mode="lines",
            line=dict(color="#a78bfa", width=1, dash="dot"),
            yaxis="y2",
        ))

    layout = dict(**_LAYOUT_BASE)
    layout["yaxis"] = dict(title="Price (USD)", gridcolor="rgba(255,255,255,0.06)")
    layout["yaxis2"] = dict(
        title="% vs Entry", overlaying="y", side="right",
        showgrid=False, zeroline=True, zerolinecolor="rgba(255,255,255,0.1)",
    )
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _wikipedia_chart(df: pd.DataFrame) -> go.Figure:
    src = df[(df["source"] == "wikipedia") & (df["metric"] == "pageviews")].sort_values("obs_date").copy()
    if src.empty:
        return _empty_fig("Wikipedia data not yet collected")

    src["roll7"] = src["value"].astype(float).rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=src["obs_date"], y=src["value"].astype(float),
        name="Daily pageviews", mode="lines",
        line=dict(color="rgba(52,211,153,0.5)", width=1),
        fill="tozeroy", fillcolor="rgba(52,211,153,0.06)",
    ))
    fig.add_trace(go.Scatter(
        x=src["obs_date"], y=src["roll7"],
        name="7d avg", mode="lines",
        line=dict(color="#10b981", width=2),
    ))
    layout = dict(**_LAYOUT_BASE)
    layout["yaxis"] = dict(title="Pageviews / day", gridcolor="rgba(255,255,255,0.06)")
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _youtube_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "youtube"]
    if src.empty:
        return _empty_fig("YouTube — not configured or no data yet")

    view_m = src[
        src["metric"].str.endswith("_views") & ~src["metric"].str.startswith("channel")
    ]
    video_ids = view_m["metric"].str.replace("_views", "", regex=False).unique().tolist()

    fig = go.Figure()
    palette = ["#f472b6", "#fb923c", "#a78bfa", "#38bdf8", "#4ade80"]

    for i, vid in enumerate(video_ids):
        c = palette[i % len(palette)]
        vr = src[src["metric"] == f"{vid}_views"].sort_values("obs_date")
        rr = src[src["metric"] == f"{vid}_like_view_ratio"].sort_values("obs_date")
        label = vr["note"].iloc[0][:35] if not vr.empty and vr["note"].iloc[0] else vid

        if not vr.empty:
            fig.add_trace(go.Scatter(
                x=vr["obs_date"], y=vr["value"].astype(float),
                name=f"{label} — views", mode="lines+markers",
                line=dict(color=c, width=2), marker=dict(size=4),
            ))
        if not rr.empty:
            fig.add_trace(go.Scatter(
                x=rr["obs_date"], y=rr["value"].astype(float),
                name=f"{label} — like/view", mode="lines+markers",
                line=dict(color=c, width=1, dash="dot"), marker=dict(size=3),
                yaxis="y2",
            ))

    ch = src[src["metric"] == "channel_views"].sort_values("obs_date")
    if not ch.empty:
        fig.add_trace(go.Scatter(
            x=ch["obs_date"], y=ch["value"].astype(float),
            name="@RockstarGames channel views", mode="lines+markers",
            line=dict(color="#94a3b8", width=1, dash="dash"), marker=dict(size=3),
        ))

    layout = dict(**_LAYOUT_BASE)
    layout["yaxis"] = dict(title="Views / Likes", gridcolor="rgba(255,255,255,0.06)")
    layout["yaxis2"] = dict(title="Like/View ratio", overlaying="y", side="right", showgrid=False)
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _polymarket_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "polymarket"]
    if src.empty:
        return _empty_fig("Polymarket — no data yet")

    fig = go.Figure()
    palette = ["#f472b6", "#60a5fa", "#34d399", "#fb923c", "#a78bfa"]
    for i, metric in enumerate(src["metric"].unique()):
        rows = src[src["metric"] == metric].sort_values("obs_date")
        note = rows["note"].iloc[0][:55] if not rows.empty else metric
        fig.add_trace(go.Scatter(
            x=rows["obs_date"], y=rows["value"].astype(float),
            name=note, mode="lines",
            line=dict(color=palette[i % len(palette)], width=2),
        ))

    fig.add_hline(
        y=0.5, line_dash="dot", line_color="rgba(255,255,255,0.15)",
        annotation_text="50%", annotation_position="bottom right",
        annotation_font_color="rgba(255,255,255,0.3)",
    )
    layout = dict(**_LAYOUT_BASE)
    layout["yaxis"] = dict(
        title="Yes probability", tickformat=".0%", range=[0, 1],
        gridcolor="rgba(255,255,255,0.06)",
    )
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _insider_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "sec"]
    if src.empty:
        return _empty_fig("SEC Form 4 — no insider filings yet")

    total = (
        src[src["metric"] == "insider_sale_usd"]
        .groupby("obs_date")["value"].sum()
        .reset_index()
    )
    discr = (
        src[src["metric"] == "insider_discretionary_usd"]
        .groupby("obs_date")["value"].sum()
        .reset_index()
        .rename(columns={"value": "discr"})
    )
    merged = total.merge(discr, on="obs_date", how="left").fillna(0)
    merged["plan"] = (merged["value"] - merged["discr"]).clip(lower=0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=merged["obs_date"], y=merged["plan"],
        name="Plan sales (10b5-1)", marker_color="rgba(148,163,184,0.65)",
    ))
    fig.add_trace(go.Bar(
        x=merged["obs_date"], y=merged["discr"],
        name="Discretionary sales", marker_color="rgba(248,113,113,0.8)",
    ))
    layout = dict(**_LAYOUT_BASE)
    layout["barmode"] = "stack"
    layout["yaxis"] = dict(
        title="Sale value (USD)", tickprefix="$", tickformat=",.0f",
        gridcolor="rgba(255,255,255,0.06)",
    )
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _gdelt_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "gdelt"]
    if src.empty:
        return _empty_fig("GDELT — no data yet")

    vol = src[src["metric"] == "media_volume"].sort_values("obs_date").copy()
    tone = src[src["metric"] == "media_tone"].sort_values("obs_date").copy()
    fig = go.Figure()

    if not vol.empty:
        vol["roll7"] = vol["value"].astype(float).rolling(7, min_periods=1).mean()
        fig.add_trace(go.Bar(
            x=vol["obs_date"], y=vol["value"].astype(float),
            name="Articles/day", marker_color="rgba(96,165,250,0.35)",
        ))
        fig.add_trace(go.Scatter(
            x=vol["obs_date"], y=vol["roll7"],
            name="Volume 7d avg", mode="lines",
            line=dict(color="#60a5fa", width=2),
        ))

    if not tone.empty:
        tone["roll7"] = tone["value"].astype(float).rolling(7, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=tone["obs_date"], y=tone["roll7"],
            name="Media sentiment (GDELT tone, 7d avg)", mode="lines",
            line=dict(color="#fbbf24", width=1.5, dash="dash"),
            yaxis="y2",
        ))

    layout = dict(**_LAYOUT_BASE)
    layout["barmode"] = "overlay"
    layout["yaxis"] = dict(title="Articles / day", gridcolor="rgba(255,255,255,0.06)")
    layout["yaxis2"] = dict(
        title="GDELT tone", overlaying="y", side="right",
        showgrid=False, zeroline=True, zerolinecolor="rgba(255,255,255,0.1)",
    )
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


def _options_chart(df: pd.DataFrame) -> go.Figure:
    src = df[df["source"] == "options"]
    if src.empty:
        return _empty_fig("Options — no data yet (snapshots accumulate forward)")

    fig = go.Figure()
    pc_colors = {"near": "#f472b6", "launch_bracket": "#fb923c"}
    iv_colors = {"near": "#a78bfa", "launch_bracket": "#38bdf8"}

    for suffix in ("near", "launch_bracket"):
        pc = src[src["metric"] == f"put_call_oi_{suffix}"].sort_values("obs_date")
        iv = src[src["metric"] == f"iv_near_{suffix}"].sort_values("obs_date")
        if not pc.empty:
            fig.add_trace(go.Scatter(
                x=pc["obs_date"], y=pc["value"].astype(float),
                name=f"P/C OI ({suffix})", mode="lines+markers",
                line=dict(color=pc_colors[suffix], width=2), marker=dict(size=5),
            ))
        if not iv.empty:
            fig.add_trace(go.Scatter(
                x=iv["obs_date"], y=iv["value"].astype(float),
                name=f"IV ATM ({suffix})", mode="lines+markers",
                line=dict(color=iv_colors[suffix], width=1.5, dash="dot"),
                marker=dict(size=4), yaxis="y2",
            ))

    fig.add_hline(
        y=1.0, line_dash="dot", line_color="rgba(255,255,255,0.15)",
        annotation_text="P/C = 1", annotation_position="bottom right",
        annotation_font_color="rgba(255,255,255,0.3)",
    )
    layout = dict(**_LAYOUT_BASE)
    layout["yaxis"] = dict(title="Put/Call OI Ratio", gridcolor="rgba(255,255,255,0.06)")
    layout["yaxis2"] = dict(title="IV (%)", overlaying="y", side="right", showgrid=False)
    fig.update_layout(**layout)
    _add_trailers(fig)
    return fig


# ---- Supporting data builders ----

def _latest_table(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    latest = (
        df.sort_values("obs_date")
        .groupby(["source", "metric"])
        .last()
        .reset_index()
    )
    rows = []
    for _, r in latest.iterrows():
        try:
            val = float(r["value"])
        except (ValueError, TypeError):
            val = r["value"]
        unit = r["unit"]
        if unit == "usd":
            formatted = f"${val:,.2f}"
        elif unit == "prob":
            formatted = f"{val:.1%}"
        elif unit == "pct":
            formatted = f"{val:+.2f}%"
        elif unit == "ratio":
            formatted = f"{val:.4f}"
        elif isinstance(val, float) and val >= 1000:
            formatted = f"{val:,.0f}"
        else:
            formatted = str(val)
        rows.append({
            "source": r["source"],
            "metric": r["metric"],
            "value": formatted,
            "unit": unit,
            "date": r["obs_date"],
        })
    return sorted(rows, key=lambda x: (x["source"], x["metric"]))


def _weekly_summary(
    df: pd.DataFrame, price: float | None, pct: float | None, days: int
) -> str:
    today = date.today().isoformat()

    def latest(source, metric) -> tuple[str, str]:
        rows = df[(df["source"] == source) & (df["metric"] == metric)].sort_values("obs_date")
        if rows.empty:
            return "N/A", "—"
        r = rows.iloc[-1]
        try:
            v = float(r["value"])
        except (ValueError, TypeError):
            return str(r["value"]), r["obs_date"]
        unit = r["unit"]
        if unit == "usd":
            fv = f"${v:,.2f}"
        elif unit == "prob":
            fv = f"{v:.1%}"
        elif unit == "pct":
            fv = f"{v:+.2f}%"
        elif unit == "ratio":
            fv = f"{v:.4f}"
        elif v >= 1000:
            fv = f"{v:,.0f}"
        else:
            fv = str(round(v, 4))
        return fv, r["obs_date"]

    price_s = f"${price:.2f}" if price is not None else "N/A"
    pct_s = f"{pct:+.1f}%" if pct is not None else "N/A"

    lines = [
        f"=== TTWO / GTA VI — {today} ===",
        f"Price:   {price_s}  ({pct_s} vs entry ${config.ENTRY_PRICE:.0f})",
        f"Launch:  {config.LAUNCH_DATE}  ({days} days away)",
        "",
        "MARKET SIGNALS",
    ]

    poly = df[df["source"] == "polymarket"]["metric"].unique().tolist() if not df.empty else []
    for pm in poly:
        nr = df[(df["source"] == "polymarket") & (df["metric"] == pm)].sort_values("obs_date")
        note = nr.iloc[-1]["note"][:50] if not nr.empty else pm
        v, dt = latest("polymarket", pm)
        lines.append(f"  {note}: {v}  [{dt}]")

    pc, pc_dt = latest("options", "put_call_oi_near")
    iv, iv_dt = latest("options", "iv_near_near")
    lines += [
        f"  Put/call OI (near):   {pc}  [{pc_dt}]",
        f"  IV near ATM:          {iv}  [{iv_dt}]",
        "",
        "ENGAGEMENT",
    ]

    wiki, wiki_dt = latest("wikipedia", "pageviews")
    gvol, gvol_dt = latest("gdelt", "media_volume")
    gtone, _ = latest("gdelt", "media_tone")
    lines += [
        f"  Wikipedia pageviews:  {wiki}/day  [{wiki_dt}]",
        f"  GDELT volume:         {gvol} articles/day  [{gvol_dt}]",
        f"  GDELT tone:           {gtone}  [{gvol_dt}]",
        "",
        "INSIDER ACTIVITY",
    ]

    ins, ins_dt = latest("sec", "insider_sale_usd")
    discr, _ = latest("sec", "insider_discretionary_usd")
    lines += [
        f"  Latest filing ({ins_dt}): {ins} total / {discr} discretionary",
        "",
        "YOUTUBE",
    ]

    yt = df[df["source"] == "youtube"] if not df.empty else pd.DataFrame()
    if not yt.empty:
        vids = (
            yt[yt["metric"].str.endswith("_views") & ~yt["metric"].str.startswith("channel")]
            ["metric"].str.replace("_views", "", regex=False).unique()
        )
        for vid in vids:
            views, vdt = latest("youtube", f"{vid}_views")
            ratio, _ = latest("youtube", f"{vid}_like_view_ratio")
            nr = yt[yt["metric"] == f"{vid}_views"].sort_values("obs_date")
            note = nr.iloc[-1]["note"][:40] if not nr.empty else vid
            lines += [
                f"  [{vid}] {note}",
                f"    Views: {views}  |  Like/view: {ratio}  [{vdt}]",
            ]
        ch_v, ch_dt = latest("youtube", "channel_views")
        ch_s, _ = latest("youtube", "channel_subs")
        lines.append(f"  @RockstarGames channel: {ch_v} views / {ch_s} subs  [{ch_dt}]")
    else:
        lines.append("  YouTube — not configured")

    lines += ["", f"Next key date: {config.LAUNCH_DATE} (GTA VI launch)"]
    return "\n".join(lines)


def _source_status(raw: dict, df: pd.DataFrame) -> dict:
    today = date.today()
    out = {}
    for src, st in raw.items():
        st = dict(st)
        last = st.get("last_success")
        if last and not st.get("skipped"):
            try:
                last_date = datetime.fromisoformat(last).date()
                st["stale"] = (today - last_date).days > config.STALE_DAYS
            except ValueError:
                st["stale"] = False
        else:
            st["stale"] = False
        out[src] = st
    return out


def main() -> None:
    df = pd.DataFrame()
    csv_path = Path(config.HISTORY_CSV)
    if csv_path.exists() and csv_path.stat().st_size > 1:
        df = pd.read_csv(csv_path, dtype={"obs_date": str, "note": str}).fillna("")

    status_path = Path(config.STATUS_JSON)
    raw_status: dict = {}
    if status_path.exists() and status_path.stat().st_size > 2:
        raw_status = json.loads(status_path.read_text())

    today = date.today()
    launch = date.fromisoformat(config.LAUNCH_DATE)
    days_to_launch = max(0, (launch - today).days)

    price_rows = (
        df[(df["source"] == "price") & (df["metric"] == "close")].sort_values("obs_date")
        if not df.empty else pd.DataFrame()
    )
    price = float(price_rows.iloc[-1]["value"]) if not price_rows.empty else None
    pct_rows = (
        df[(df["source"] == "price") & (df["metric"] == "pct_vs_entry")].sort_values("obs_date")
        if not df.empty else pd.DataFrame()
    )
    pct = float(pct_rows.iloc[-1]["value"]) if not pct_rows.empty else None

    src_status = _source_status(raw_status, df)

    def _last_date(src: str) -> str:
        rows = df[df["source"] == src] if not df.empty else pd.DataFrame()
        return rows["obs_date"].max() if not rows.empty else "—"

    builders = [
        ("Price — TTWO", "price", _price_chart),
        ("Wikipedia Pageviews", "wikipedia", _wikipedia_chart),
        ("YouTube — Views & Engagement", "youtube", _youtube_chart),
        ("Polymarket — Yes Probabilities", "polymarket", _polymarket_chart),
        ("SEC Form 4 — Insider Sales", "sec", _insider_chart),
        ("GDELT — Media Coverage & Tone", "gdelt", _gdelt_chart),
        ("Options — Put/Call OI & IV", "options", _options_chart),
    ]
    charts = []
    for title, src, builder in builders:
        st = src_status.get(src, {})
        charts.append({
            "title": title,
            "source": src,
            "div": _div(builder(df)),
            "last_updated": _last_date(src),
            "stale": st.get("stale", False),
            "unavailable": not st.get("ok", True),
            "skipped": st.get("skipped", False),
        })

    # Pre-formatted header values so the template needs no math
    price_str = f"${price:.2f}" if price is not None else "—"
    pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
    pct_positive = (pct or 0) >= 0

    env = Environment(loader=FileSystemLoader("templates"), autoescape=False)
    tmpl = env.get_template("dashboard.html.j2")
    html = tmpl.render(
        last_updated=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        backfill_start=config.BACKFILL_START_DATE,
        days_to_launch=days_to_launch,
        launch_date=config.LAUNCH_DATE,
        price_str=price_str,
        pct_str=pct_str,
        pct_positive=pct_positive,
        price_available=(price is not None),
        entry_price_str=f"${config.ENTRY_PRICE:.0f}",
        source_status=src_status,
        charts=charts,
        latest_rows=_latest_table(df),
        weekly_summary=_weekly_summary(df, price, pct, days_to_launch),
    )

    Path(config.DOCS_DIR).mkdir(exist_ok=True)
    out = Path(config.DOCS_DIR) / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written -> {out}")


if __name__ == "__main__":
    main()
