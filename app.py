"""
app.py (Version 2.0 – Mit Sell-Signalen & Backtest-Tab)
Streamlit-Dashboard für den Cycle Turnaround Tracker.
"""

import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import SEGMENTS, THRESHOLDS, DB_PATH
import database as db
import backtester

st.set_page_config(page_title="Cycle Turnaround Tracker", page_icon="📈", layout="wide")

SIGNAL_BADGES = {
    "BUY": "🟢 BUY (Entry)",
    "HOLD": "🔵 HOLD (Long)",
    "ORANGE": "🟠 ORANGE (Warnung)",
    "SELL": "🔴 SELL (Exit)",
    "GELB": "🟡 GELB (Watchlist)",
    "BLAU": "🔵 BLAU (Mid-Cycle)",
    "ROT": "⚫ ROT (Flat/Ab)",
}

SIGNAL_ORDER = {"BUY": 0, "ORANGE": 1, "SELL": 2, "GELB": 3, "HOLD": 4, "BLAU": 5, "ROT": 6}

st.title("📈 Cycle Turnaround Tracker V2.0")
st.caption("10 Sub-Segmente · 60 Indikatoren · Positions-State-Machine (BUY / ORANGE / SELL) · Live-Backtester")

if not os.path.exists(DB_PATH):
    st.warning("Datenbank `cycle_data.db` fehlt noch. Bitte zuerst den GitHub-Actions-Workflow starten.")
    st.stop()

last_run = db.get_last_run_info()
if last_run:
    run_at, run_status, run_msg = last_run
    st.info(f"**Letztes Update:** {run_at} | **Status:** {run_status} — {run_msg}")

tab_overview, tab_backtest = st.tabs(["📊 Zyklus-Dashboard", "🧪 Backtest & Validierung"])

# ==============================================================================
# TAB 1: ÜBERSICHT & DETAIL-ANALYSE
# ==============================================================================
with tab_overview:
    st.subheader("1. Übersichts-Matrix")
    latest_map = db.get_latest_two_segment_signals()
    matrix_rows = []

    for seg_id, seg_cfg in SEGMENTS.items():
        data = latest_map.get(seg_id, {})
        curr = data.get("current")
        prev = data.get("previous")
        if not curr:
            continue

        delta_1w = (curr["s_total"] - prev["s_total"]) if prev else 0.0
        sig = curr["signal"]

        matrix_rows.append({
            "_sort": SIGNAL_ORDER.get(sig, 9),
            "Segment": seg_cfg["name"],
            "Signal": SIGNAL_BADGES.get(sig, sig),
            "Gesamt-Score": round(curr["s_total"], 1),
            "Δ 1W": round(delta_1w, 1),
            "Nachfrage (50%)": round(curr["s_demand"], 1) if pd.notna(curr["s_demand"]) else None,
            "Kapazität (30%)": round(curr["s_capacity"], 1) if pd.notna(curr["s_capacity"]) else None,
            "Preis (20%)": round(curr["s_price"], 1) if pd.notna(curr["s_price"]) else None,
            "Stand": curr["date"],
        })

    df_matrix = pd.DataFrame(matrix_rows).sort_values(
        by=["_sort", "Gesamt-Score"], ascending=[True, False]
    ).drop(columns=["_sort"])

    st.dataframe(
        df_matrix,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Gesamt-Score": st.column_config.ProgressColumn("Gesamt-Score", min_value=0, max_value=100, format="%.1f"),
            "Δ 1W": st.column_config.NumberColumn("Δ 1W", format="%+.1f"),
        },
    )

    st.divider()
    st.subheader("2. Detail-Analyse")

    seg_options = {seg_cfg["name"]: seg_id for seg_id, seg_cfg in SEGMENTS.items()}
    selected_name = st.selectbox("Sub-Segment auswählen:", list(seg_options.keys()), key="ov_seg")
    selected_seg_id = seg_options[selected_name]

    hist_df = db.get_segment_history(selected_seg_id)
    cutoff = hist_df["date"].max() - pd.DateOffset(years=5)
    hist_5y = hist_df[hist_df["date"] >= cutoff].copy()

    # Chart 1: Gesamt-Score + BUY / ORANGE / SELL Marker
    fig_total = go.Figure()
    fig_total.add_hrect(y0=0, y1=THRESHOLDS["bottom_level"], fillcolor="rgba(239, 68, 68, 0.08)", line_width=0)
    fig_total.add_hrect(y0=THRESHOLDS["orange_min"], y1=100, fillcolor="rgba(249, 115, 22, 0.08)", line_width=0)

    fig_total.add_trace(go.Scatter(
        x=hist_5y["date"], y=hist_5y["s_total"],
        mode="lines", name="Gesamt-Score", line=dict(color="#3b82f6", width=2.5),
    ))

    for sig_code, label, color, symbol in [
        ("BUY", "🟢 BUY", "#16a34a", "triangle-up"),
        ("ORANGE", "🟠 ORANGE", "#f97316", "diamond"),
        ("SELL", "🔴 SELL", "#dc2626", "triangle-down"),
    ]:
        pts = hist_5y[hist_5y["signal"] == sig_code]
        if not pts.empty:
            fig_total.add_trace(go.Scatter(
                x=pts["date"], y=pts["s_total"],
                mode="markers", name=label,
                marker=dict(color=color, size=11, symbol=symbol, line=dict(color="white", width=1)),
            ))

    fig_total.add_hline(y=THRESHOLDS["bottom_level"], line_dash="dash", line_color="#dc2626", annotation_text="Boden (25)")
    fig_total.add_hline(y=THRESHOLDS["orange_min"], line_dash="dash", line_color="#f97316", annotation_text="Überhitzt (70)")

    fig_total.update_layout(
        title=f"Gesamt-Score & Signale (5 Jahre) – {selected_name}",
        yaxis=dict(title="Score (0–100)", range=[0, 100]),
        hovermode="x unified", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_total, use_container_width=True)

    # Chart 2: Sub-Scores
    fig_sub = go.Figure()
    fig_sub.add_trace(go.Scatter(x=hist_5y["date"], y=hist_5y["s_demand"], mode="lines", name="Nachfrage (50%)", line=dict(color="#16a34a", width=2)))
    fig_sub.add_trace(go.Scatter(x=hist_5y["date"], y=hist_5y["s_capacity"], mode="lines", name="Kapazität (30%)", line=dict(color="#f59e0b", width=2)))
    fig_sub.add_trace(go.Scatter(x=hist_5y["date"], y=hist_5y["s_price"], mode="lines", name="Preis/Marge (20%)", line=dict(color="#8b5cf6", width=2)))
    fig_sub.update_layout(
        title="Sub-Scores im Zeitverlauf", yaxis=dict(range=[0, 100]),
        hovermode="x unified", height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_sub, use_container_width=True)

    # Tabelle: Einzelindikatoren
    st.markdown("#### Aktuelle Einzelindikatoren")
    ind_details = db.get_latest_indicator_details(selected_seg_id)
    ind_meta = {ind["id"]: ind for ind in SEGMENTS[selected_seg_id]["indicators"]}
    detail_rows = []
    for ind_id, meta in ind_meta.items():
        match = ind_details[ind_details["indicator_id"] == ind_id]
        if not match.empty:
            row = match.iloc[0]
            detail_rows.append({
                "Indikator": meta["name"],
                "Kategorie": meta["category"],
                "Invertiert": "Ja" if meta.get("invert") else "Nein",
                "Rohwert": round(row["raw_value"], 3) if pd.notna(row["raw_value"]) else None,
                "Perzentil": round(row["percentile"], 1) if pd.notna(row["percentile"]) else None,
                "Update": row["date"],
                "Status": "✅ OK" if row["status"] == "OK" else f"⚠️ {row['status']}",
            })
        else:
            detail_rows.append({"Indikator": meta["name"], "Kategorie": meta["category"], "Invertiert": "Ja" if meta.get("invert") else "Nein", "Rohwert": None, "Perzentil": None, "Update": "—", "Status": "❌ Fehlt"})
    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 2: BACKTEST & VALIDIERUNG
# ==============================================================================
with tab_backtest:
    st.subheader("🧪 Strategie-Backtest mit ETFs & Einzelaktien")

    col1, col2, col3, col4 = st.columns([2, 1.5, 1, 1.5])
    with col1:
        bt_seg_name = st.selectbox("Segment:", list(seg_options.keys()), key="bt_seg")
        bt_seg_id = seg_options[bt_seg_name]
    with col2:
        seg_cfg = SEGMENTS[bt_seg_id]
        asset_choices = [seg_cfg["benchmark_etf"]] + seg_cfg["stocks"]
        bt_ticker = st.selectbox("ETF / Aktie:", asset_choices)
    with col3:
        use_dl = st.checkbox("Double-Lock (10W-EMA)", value=True)
    with col4:
        ts_pct = st.slider("Trailing-Stop (%)", min_value=0, max_value=35, value=15, step=5) / 100.0

    bt_hist = db.get_segment_history(bt_seg_id)
    with st.spinner(f"Berechne Backtest für {bt_ticker}..."):
        res = backtester.run_backtest(
            bt_hist, bt_ticker,
            use_double_lock=use_dl,
            ema_weeks=THRESHOLDS["double_lock_ema_wks"],
            trailing_stop_pct=ts_pct,
        )

    if "error" in res:
        st.error(res["error"])
    else:
        m = res["metrics"]
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Strategie-Rendite", f"{m['strat_return']:+.1f} %")
        k2.metric("Buy & Hold", f"{m['bh_return']:+.1f} %", delta=f"{m['strat_return'] - m['bh_return']:+.1f} % Alpha")
        k3.metric("Max Drawdown (Strat.)", f"{m['max_dd_strat']:.1f} %")
        k4.metric("Max Drawdown (B&H)", f"{m['max_dd_bh']:.1f} %")
        k5.metric("Win-Rate / Trades", f"{m['win_rate']:.0f} % ({m['num_trades']})")

        bt_df = res["df"]

        # Overlay-Chart: Kurs + Zyklus-Score + BUY/SELL-Dreiecke
        fig_bt = make_subplots(specs=[[{"secondary_y": True}]])
        fig_bt.add_trace(
            go.Scatter(x=bt_df["date"], y=bt_df["price"], name=f"{bt_ticker} Kurs", line=dict(color="#10b981", width=2.5)),
            secondary_y=False,
        )
        fig_bt.add_trace(
            go.Scatter(x=bt_df["date"], y=bt_df["s_total"], name="Zyklus-Score", line=dict(color="rgba(59,130,246,0.45)", width=1.8)),
            secondary_y=True,
        )

        if res["buy_points"]:
            bx, by, _ = zip(*res["buy_points"])
            fig_bt.add_trace(
                go.Scatter(x=bx, y=by, mode="markers", name="🟢 BUY", marker=dict(color="#16a34a", size=13, symbol="triangle-up")),
                secondary_y=False,
            )
        if res["sell_points"]:
            sx, sy, s_txt = zip(*res["sell_points"])
            fig_bt.add_trace(
                go.Scatter(x=sx, y=sy, mode="markers", name="🔴 SELL", text=s_txt, marker=dict(color="#dc2626", size=13, symbol="triangle-down")),
                secondary_y=False,
            )

        fig_bt.update_layout(
            title=f"{bt_ticker} Kurs vs. Zyklus-Score ({bt_seg_name})",
            hovermode="x unified", height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig_bt.update_yaxes(title_text=f"{bt_ticker} Kurs", secondary_y=False)
        fig_bt.update_yaxes(title_text="Zyklus-Score (0–100)", range=[0, 100], secondary_y=True)
        st.plotly_chart(fig_bt, use_container_width=True)

        # Equity-Kurve: Strategie vs. Buy & Hold
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=bt_df["date"], y=bt_df["strategy_equity"], name="Strategie (Start = 100)", line=dict(color="#16a34a", width=2.5)))
        fig_eq.add_trace(go.Scatter(x=bt_df["date"], y=bt_df["bh_equity"], name="Buy & Hold (Start = 100)", line=dict(color="#94a3b8", width=2, dash="dot")))
        fig_eq.update_layout(title="Kapitalentwicklung (Indexiert auf 100)", hovermode="x unified", height=320)
        st.plotly_chart(fig_eq, use_container_width=True)

        st.markdown("#### Trade-Historie")
        if not res["trades"].empty:
            st.dataframe(res["trades"], use_container_width=True, hide_index=True)
        else:
            st.info("Keine Trades im gewählten Zeitraum ausgelöst.")
