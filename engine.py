"""
engine.py
Berechnet rollierende 5-Jahres-Perzentile, gewichtete Kategorie-Scores
und die Ampel-State-Machine (ROT / GELB / GRUEN / BLAU) für alle 10 Segmente.
"""

import numpy as np
import pandas as pd

from config import SEGMENTS, ROLLING_WINDOW_WEEKS, CATEGORY_WEIGHTS, THRESHOLDS
import database as db


def _rolling_percentile(series: pd.Series, window: int = ROLLING_WINDOW_WEEKS) -> pd.Series:
    """
    Berechnet den rollierenden Perzentil-Rang (0 bis 100) über die letzten
    'window' Wochen. Nutzt mindestens 26 Wochen Historie als Minimum.
    """
    def _pct_rank(arr):
        valid = arr[~np.isnan(arr)]
        if len(valid) < 2:
            return np.nan
        current = valid[-1]
        # Anteil der Werte <= aktuellem Wert (in Prozent)
        return (np.sum(valid <= current) / len(valid)) * 100.0

    return series.rolling(window=window, min_periods=26).apply(_pct_rank, raw=True)


def _evaluate_signal(df: pd.DataFrame) -> pd.Series:
    """
    Wendet die Ampel-State-Machine zeilenweise auf einen Segment-DataFrame an.
    Spalten benötigt: ['s_total', 's_demand']
    """
    signals = []
    s_total = df["s_total"].values
    s_demand = df["s_demand"].values

    # 4-Wochen-Durchschnitt der Nachfrage für Bedingung 3
    demand_ma = df["s_demand"].rolling(
        window=THRESHOLDS["demand_ma_wks"], min_periods=1
    ).mean().values

    lookback = THRESHOLDS["bottom_lookback_wks"]
    bottom_lvl = THRESHOLDS["bottom_level"]
    green_min = THRESHOLDS["green_min"]
    green_max = THRESHOLDS["green_max"]

    for i in range(len(df)):
        curr = s_total[i]
        if np.isnan(curr):
            signals.append("ROT")
            continue

        # 1. BLAU: Mid-to-Late Cycle / Halten
        if curr > green_max:
            signals.append("BLAU")
            continue

        # Prüfen, ob genug Historie für Trendvergleich da ist
        prev1 = s_total[i - 1] if i >= 1 else np.nan
        prev2 = s_total[i - 2] if i >= 2 else np.nan

        # 2. GRÜN: Bestätigter Turnaround (alle 3 Bedingungen gleichzeitig)
        start_idx = max(0, i - lookback)
        recent_window = s_total[start_idx : i + 1]
        had_bottom = bool(np.nanmin(recent_window) < bottom_lvl) if len(recent_window) > 0 else False

        two_weeks_up = (
            not np.isnan(prev1)
            and not np.isnan(prev2)
            and (curr > prev1 > prev2)
            and (green_min <= curr <= green_max)
        )

        demand_confirmed = (
            not np.isnan(s_demand[i])
            and not np.isnan(demand_ma[i])
            and (s_demand[i] > demand_ma[i])
        )

        if had_bottom and two_weeks_up and demand_confirmed:
            signals.append("GRUEN")
            continue

        # 3. GELB: Watchlist / Früher Boden
        if curr < bottom_lvl and not np.isnan(prev1) and curr > prev1:
            signals.append("GELB")
            continue

        # 4. ROT: Abschwung / Bodenbildung
        signals.append("ROT")

    return pd.Series(signals, index=df.index)


def run_scoring_engine():
    """
    Berechnet für alle 10 Segmente und 60 Indikatoren die Perzentile,
    Kategorie-Scores und Ampel-Signale und speichert sie in SQLite.
    """
    print("Starte Scoring-Engine...")
    all_indicator_rows = []
    all_segment_rows = []

    for seg_id, seg_cfg in SEGMENTS.items():
        cat_series = {"demand": [], "capacity": [], "price": []}

        for ind in seg_cfg["indicators"]:
            ind_id = ind["id"]
            raw_df = db.get_raw_series(ind_id)

            if raw_df.empty:
                continue

            pct = _rolling_percentile(raw_df["raw_value"], ROLLING_WINDOW_WEEKS)

            # Kontrazyklische Indikatoren invertieren (hoher Score = immer bullisch)
            if ind.get("invert", False):
                pct = 100.0 - pct

            cat_series[ind["category"]].append(pct.rename(ind_id))

            # Einzelindikator-Scores für die DB sammeln
            ind_df = pd.DataFrame({
                "date": raw_df.index.strftime("%Y-%m-%d"),
                "indicator_id": ind_id,
                "segment_id": seg_id,
                "raw_value": raw_df["raw_value"].values,
                "percentile": pct.values,
                "status": raw_df["status"].values,
            }).dropna(subset=["percentile"])
            all_indicator_rows.append(ind_df)

        # Kategorie-Durchschnitte bilden
        df_demand = pd.concat(cat_series["demand"], axis=1).mean(axis=1) if cat_series["demand"] else pd.Series(dtype=float)
        df_capacity = pd.concat(cat_series["capacity"], axis=1).mean(axis=1) if cat_series["capacity"] else pd.Series(dtype=float)
        df_price = pd.concat(cat_series["price"], axis=1).mean(axis=1) if cat_series["price"] else pd.Series(dtype=float)

        seg_df = pd.DataFrame({
            "s_demand": df_demand,
            "s_capacity": df_capacity,
            "s_price": df_price,
        }).dropna(how="all")

        if seg_df.empty:
            continue

        # Gewichteter Gesamt-Score (dynamische Normierung, falls eine Kategorie fehlt)
        w_d = CATEGORY_WEIGHTS["demand"]
        w_c = CATEGORY_WEIGHTS["capacity"]
        w_p = CATEGORY_WEIGHTS["price"]

        seg_df["s_total"] = (
            seg_df["s_demand"].fillna(50.0) * w_d
            + seg_df["s_capacity"].fillna(50.0) * w_c
            + seg_df["s_price"].fillna(50.0) * w_p
        )

        # Ampel-State-Machine anwenden
        seg_df["signal"] = _evaluate_signal(seg_df)
        seg_df["segment_id"] = seg_id
        seg_df["date"] = seg_df.index.strftime("%Y-%m-%d")

        all_segment_rows.append(
            seg_df[["date", "segment_id", "s_demand", "s_capacity", "s_price", "s_total", "signal"]]
        )

    if all_indicator_rows:
        db.save_indicator_scores(pd.concat(all_indicator_rows, ignore_index=True))

    if all_segment_rows:
        db.save_segment_scores(pd.concat(all_segment_rows, ignore_index=True))

    print("Scoring-Engine erfolgreich abgeschlossen.")