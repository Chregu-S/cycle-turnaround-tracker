"""
engine.py (Version 2.0 – Positions-State-Machine mit BUY & SELL)
Berechnet 5-Jahres-Perzentile, Kategorie-Scores und echte Trading-Zustände:
- BUY    (🟢): Einmaliger Einstieg nach bestätigtem Boden
- HOLD   (🔵): Offene Long-Position läuft
- ORANGE (🟠): Frühwarnung / Teilverkauf (Score > 70 & Nachfrage dreht ab)
- SELL   (🔴): Hard Exit (Peak > 65 & 2 Wochen fallend, oder Notbremse < 25)
- GELB   (🟡): Watchlist (früher Boden, noch nicht bestätigt)
- ROT    (⚫): Neutral / Abschwung (Flat)
"""

import numpy as np
import pandas as pd

from config import SEGMENTS, ROLLING_WINDOW_WEEKS, CATEGORY_WEIGHTS, THRESHOLDS
import database as db


def _rolling_percentile(series: pd.Series, window: int = ROLLING_WINDOW_WEEKS) -> pd.Series:
    def _pct_rank(arr):
        valid = arr[~np.isnan(arr)]
        if len(valid) < 2:
            return np.nan
        current = valid[-1]
        return (np.sum(valid <= current) / len(valid)) * 100.0

    return series.rolling(window=window, min_periods=26).apply(_pct_rank, raw=True)


def _evaluate_signal(df: pd.DataFrame) -> pd.Series:
    """
    Positions-State-Machine (FLAT <-> LONG):
    Verhindert doppelte BUY-Signale und erzeugt saubere ORANGE- & SELL-Exits.
    """
    signals = []
    s_total = df["s_total"].values
    s_demand = df["s_demand"].values

    demand_ma = df["s_demand"].rolling(
        window=THRESHOLDS["demand_ma_wks"], min_periods=1
    ).mean().values

    in_position = False  # Merkt sich, ob wir aktuell LONG sind

    for i in range(len(df)):
        curr = s_total[i]
        if np.isnan(curr):
            signals.append("ROT")
            continue

        prev1 = s_total[i - 1] if i >= 1 else np.nan
        prev2 = s_total[i - 2] if i >= 2 else np.nan

        demand_up = (
            not np.isnan(s_demand[i])
            and not np.isnan(demand_ma[i])
            and (s_demand[i] > demand_ma[i])
        )
        demand_down = (
            not np.isnan(s_demand[i])
            and not np.isnan(demand_ma[i])
            and (s_demand[i] < demand_ma[i])
        )

        # ------------------------------------------------------------------
        # FALL A: WIR SIND AKTUELL NICHT INVESTIERT (FLAT)
        # ------------------------------------------------------------------
        if not in_position:
            start_idx = max(0, i - THRESHOLDS["bottom_lookback_wks"])
            recent_window = s_total[start_idx : i + 1]
            had_bottom = bool(np.nanmin(recent_window) < THRESHOLDS["bottom_level"])

            two_weeks_up = (
                not np.isnan(prev1)
                and not np.isnan(prev2)
                and (curr > prev1 > prev2)
                and (THRESHOLDS["green_min"] <= curr <= THRESHOLDS["green_max"])
            )

            if had_bottom and two_weeks_up and demand_up:
                signals.append("BUY")
                in_position = True
            elif curr < THRESHOLDS["bottom_level"] and not np.isnan(prev1) and curr > prev1:
                signals.append("GELB")
            elif curr > THRESHOLDS["green_max"]:
                signals.append("BLAU")
            else:
                signals.append("ROT")

        # ------------------------------------------------------------------
        # FALL B: WIR SIND AKTUELL INVESTIERT (LONG)
        # ------------------------------------------------------------------
        else:
            peak_start = max(0, i - THRESHOLDS["sell_lookback_wks"])
            peak_window = s_total[peak_start : i + 1]
            had_peak = bool(np.nanmax(peak_window) > THRESHOLDS["sell_peak_level"])

            two_weeks_down = (
                not np.isnan(prev1)
                and not np.isnan(prev2)
                and (curr < prev1 < prev2)
            )

            # 1. Hard Exit (Makro-Peak gebrochen ODER harter Rückfall < 25)
            if (had_peak and two_weeks_down) or (curr < THRESHOLDS["hard_stop_score"] and two_weeks_down):
                signals.append("SELL")
                in_position = False
            # 2. Frühwarnung / Teilverkauf (Überhitzt + Nachfrage dreht ab)
            elif curr > THRESHOLDS["orange_min"] and demand_down:
                signals.append("ORANGE")
            # 3. Weiter laufen lassen
            else:
                signals.append("HOLD")

    return pd.Series(signals, index=df.index)


def run_scoring_engine():
    print("Starte Scoring-Engine (V2.0)...")
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
            if ind.get("invert", False):
                pct = 100.0 - pct

            cat_series[ind["category"]].append(pct.rename(ind_id))

            ind_df = pd.DataFrame({
                "date": raw_df.index.strftime("%Y-%m-%d"),
                "indicator_id": ind_id,
                "segment_id": seg_id,
                "raw_value": raw_df["raw_value"].values,
                "percentile": pct.values,
                "status": raw_df["status"].values,
            }).dropna(subset=["percentile"])
            all_indicator_rows.append(ind_df)

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

        seg_df["s_total"] = (
            seg_df["s_demand"].fillna(50.0) * CATEGORY_WEIGHTS["demand"]
            + seg_df["s_capacity"].fillna(50.0) * CATEGORY_WEIGHTS["capacity"]
            + seg_df["s_price"].fillna(50.0) * CATEGORY_WEIGHTS["price"]
        )

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

    print("Scoring-Engine V2.0 abgeschlossen.")
