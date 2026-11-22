"""
app.py
Streamlit-Dashboard für den Cycle Turnaround Tracker.
Start lokal mit: streamlit run app.py
"""

import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import SEGMENTS, THRESHOLDS, DB_PATH
import database as db

# ==============================================================================
# SEITEN-KONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="Cycle Turnaround Tracker",
    page_icon="📈",
    layout="wide",
)

SIGNAL_BADGES = {
    "GRUEN": "🟢 GRÜN (Entry)",
    "GELB": "🟡 GELB (Watchlist)",
    "BLAU": "🔵 BLAU (Mid-Cycle)",
    "ROT": "🔴 ROT (Abschwung)",
}

SIGNAL_ORDER = {"GRUEN": 0, "GELB": 1, "BLAU": 2, "ROT": 3}

# ==============================================================================
# HEADER & DATENBANK-CHECK
# ==============================================================================
st.title("📈 Cycle Turnaround Tracker")
st.caption("Wöchentliches Zykliker-Dashboard – 10 Sub-Segmente · 60 Indikatoren · 5-Jahres-Perzentile")

if not os.path.exists(DB_PATH):
    st.warning(
        "Die Datenbank `cycle_data.db` existiert noch nicht. "
        "Führe zuerst `python run_weekly.py` aus (oder starte den GitHub-Actions-Workflow)."
    )
    st.stop()

last_run = db.get_last_run_info()
if last_run:
    run_at, run_status, run_msg = last_run
    st.info(f"**Letztes Update:** {run_at} | **Status:** {run_status} — {run_msg}")

# ==============================================================================
# 1. ÜBERSICHTS-MATRIX (ALLE 10 SUB-SEGMENTE)
# ==============================================================================
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
        "Ampel": SIGNAL_BADGES.get(sig, sig),
        "Gesamt-Score": round(curr["s_total"], 1),
        "Δ 1W": round(delta_1w, 1),
        "Nachfrage (50%)": round(curr["s_demand"], 1),
        "Kapazität/Lager (30%)": round(curr["s_capacity"], 1),
        "Preis/Marge (20%)": round(curr["s_price"], 1),
        "Stand": curr["date"],
    })

if not matrix_rows:
    st.error("Keine berechneten Segment-Scores in der Datenbank gefunden.")
    st.stop()

df_matrix = pd.DataFrame(matrix_rows).sort_values(
    by=["_sort", "Gesamt-Score"], ascending=[True, False]
).drop(columns=["_sort"])

st.dataframe(
    df_matrix,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Gesamt-Score": st.column_config.ProgressColumn(
            "Gesamt-Score", min_value=0, max_value=100, format="%.1f"
        ),
        "Δ 1W": st.column_config.NumberColumn("Δ 1W", format="%+.1f"),
        "Nachfrage (50%)": st.column_config.NumberColumn("Nachfrage (50%)", format="%.1f"),
        "Kapazität/Lager (30%)": st.column_config.NumberColumn("Kapazität/Lager (30%)", format="%.1f"),
        "Preis/Marge (20%)": st.column_config.NumberColumn("Preis/Marge (20%)", format="%.1f"),
    },
)

st.divider()

# ==============================================================================
# 2. DETAIL-ANSICHT PRO SUB-SEGMENT
# ==============================================================================
st.subheader("2. Detail-Analyse")

seg_options = {seg_cfg["name"]: seg_id for seg_id, seg_cfg in SEGMENTS.items()}
selected_name = st.selectbox("Sub-Segment auswählen:", list(seg_options.keys()))
selected_seg_id = seg_options[selected_name]

hist_df = db.get_segment_history(selected_seg_id)

if hist_df.empty:
    st.warning("Für dieses Segment liegen noch keine historischen Daten vor.")
    st.stop()

# Auf die letzten 5 Jahre begrenzen
cutoff = hist_df["date"].max() - pd.DateOffset(years=5)
hist_5y = hist_df[hist_df["date"] >= cutoff].copy()

# --- Chart 1: Gesamt-Score + Schwellenlinien + Historische GRÜN-Entry-Punkte ---
fig_total = go.Figure()

# Hintergrund-Zonen
fig_total.add_hrect(y0=0, y1=THRESHOLDS["bottom_level"], fillcolor="rgba(239, 68, 68, 0.08)", line_width=0)
fig_total.add_hrect(y0=THRESHOLDS["green_max"], y1=100, fillcolor="rgba(59, 130, 246, 0.08)", line_width=0)

# Hauptlinie Gesamt-Score
fig_total.add_trace(go.Scatter(
    x=hist_5y["date"],
    y=hist_5y["s_total"],
    mode="lines",
    name="Gesamt-Score (S_Total)",
    line=dict(color="#1f77b4", width=2.5),
))

# Historische GRÜN-Entry-Punkte markieren
green_pts = hist_5y[hist_5y["signal"] == "GRUEN"]
if not green_pts.empty:
    fig_total.add_trace(go.Scatter(
        x=green_pts["date"],
        y=green_pts["s_total"],
        mode="markers",
        name="🟢 GRÜN Entry-Signal",
        marker=dict(color="#16a34a", size=9, symbol="circle", line=dict(color="white", width=1.5)),
    ))

# Schwellenlinien (25 = Boden, 55 = Mid-Cycle)
fig_total.add_hline(
    y=THRESHOLDS["bottom_level"],
    line_dash="dash",
    line_color="#dc2626",
    annotation_text="Boden (25)",
    annotation_position="bottom right",
)
fig_total.add_hline(
    y=THRESHOLDS["green_max"],
    line_dash="dash",
    line_color="#2563eb",
    annotation_text="Mid-Cycle (55)",
    annotation_position="top right",
)

fig_total.update_layout(
    title=f"Gesamt-Score (5 Jahre) – {selected_name}",
    yaxis=dict(title="Score (0–100)", range=[0, 100]),
    xaxis=dict(title=""),
    hovermode="x unified",
    height=420,
    margin=dict(l=20, r=20, t=50, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_total, use_container_width=True)

# --- Chart 2: Die 3 Sub-Scores im Zeitverlauf (Sequenzielle Drehung) ---
fig_sub = go.Figure()

fig_sub.add_trace(go.Scatter(
    x=hist_5y["date"], y=hist_5y["s_demand"],
    mode="lines", name="Nachfrage (50%)", line=dict(color="#16a34a", width=2),
))
fig_sub.add_trace(go.Scatter(
    x=hist_5y["date"], y=hist_5y["s_capacity"],
    mode="lines", name="Kapazität/Lager (30%)", line=dict(color="#f59e0b", width=2),
))
fig_sub.add_trace(go.Scatter(
    x=hist_5y["date"], y=hist_5y["s_price"],
    mode="lines", name="Preis/Marge (20%)", line=dict(color="#8b5cf6", width=2),
))

fig_sub.update_layout(
    title="Sub-Scores im Zeitverlauf (Nachfrage → Kapazität → Preis)",
    yaxis=dict(title="Perzentil-Score (0–100)", range=[0, 100]),
    xaxis=dict(title=""),
    hovermode="x unified",
    height=350,
    margin=dict(l=20, r=20, t=50, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_sub, use_container_width=True)

# --- Tabelle: Die 6 Roh-Indikatoren des gewählten Segments ---
st.markdown("#### Aktuelle Einzelindikatoren")

ind_details = db.get_latest_indicator_details(selected_seg_id)
ind_meta = {ind["id"]: ind for ind in SEGMENTS[selected_seg_id]["indicators"]}
cat_labels = {"demand": "Nachfrage (50%)", "capacity": "Kapazität/Lager (30%)", "price": "Preis/Marge (20%)"}

detail_rows = []
for ind_id, meta in ind_meta.items():
    match = ind_details[ind_details["indicator_id"] == ind_id]
    if not match.empty:
        row = match.iloc[0]
        raw_val = round(row["raw_value"], 3) if pd.notna(row["raw_value"]) else None
        pct_val = round(row["percentile"], 1) if pd.notna(row["percentile"]) else None
        dt_val = row["date"]
        st_val = "✅ OK" if row["status"] == "OK" else f"⚠️ {row['status']}"
    else:
        raw_val, pct_val, dt_val, st_val = None, None, "—", "❌ Fehlt"

    detail_rows.append({
        "Indikator": meta["name"],
        "Kategorie": cat_labels.get(meta["category"], meta["category"]),
        "Invertiert": "Ja" if meta.get("invert") else "Nein",
        "Rohwert": raw_val,
        "Perzentil-Score": pct_val,
        "Letztes Update": dt_val,
        "Status": st_val,
    })

st.dataframe(
    pd.DataFrame(detail_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Perzentil-Score": st.column_config.ProgressColumn(
            "Perzentil-Score", min_value=0, max_value=100, format="%.1f"
        ),
    },
)