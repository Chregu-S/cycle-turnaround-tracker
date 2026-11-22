"""
portfolio_backtester.py (Version 3.3 – Smart Parking & Top-N Active Only)
Vergleicht 3 saubere Strategien (nie in ROT-Sektoren) direkt gegen SPY:
1. Smart Parking (Alle Aktiven): Alle BUY/HOLD-Sektoren (mit Cap) + Rest in SPY (oder SHY bei VIX>25 & SPY<200DMA)
2. Top-N Active + Smart Parking: Max. Top N aktive BUY/HOLD-Sektoren (nach EMA6-EMA20) + Rest im Smart Parking
3. Reiner 200DMA-Parkplatz: Alle BUY/HOLD-Sektoren + Rest in SPY (oder SHY bei SPY<200DMA)
"""

import numpy as np
import pandas as pd
from config import SEGMENTS, THRESHOLDS
import database as db
import backtester


def _calc_metrics(eq: pd.Series, name: str) -> dict:
    tot_ret = (float(eq.iloc[-1]) / float(eq.iloc[0]) - 1.0) * 100.0
    years = max(0.5, (eq.index[-1] - eq.index[0]).days / 365.25)
    cagr = ((float(eq.iloc[-1]) / float(eq.iloc[0])) ** (1.0 / years) - 1.0) * 100.0

    roll_max = eq.cummax()
    max_dd = float(((eq - roll_max) / roll_max).min() * 100.0)
    calmar = round(cagr / abs(max_dd), 2) if max_dd < 0 else 0.0

    return {
        "Strategie": name,
        "Total Return (%)": round(tot_ret, 1),
        "CAGR (%/yr)": round(cagr, 1),
        "Max Drawdown (%)": round(max_dd, 1),
        "CAGR / Max DD": calmar,
    }


def run_portfolio_backtest(
    max_sector_weight: float = 0.35,
    top_n_active: int = 3,
    vix_threshold: float = 25.0,
) -> dict:
    fast_span = THRESHOLDS.get("regime_fast_ema", 6)
    slow_span = THRESHOLDS.get("regime_slow_ema", 20)

    prices_dict = {}
    bullish_dict = {}
    momentum_dict = {}

    earliest_dates = []
    for seg_id, seg_cfg in SEGMENTS.items():
        hist = db.get_segment_history(seg_id)
        if hist.empty:
            continue
        hist = hist.set_index("date").sort_index()
        earliest_dates.append(hist.index.min())

        ema_f = hist["s_total"].ewm(span=fast_span, adjust=False).mean()
        ema_s = hist["s_total"].ewm(span=slow_span, adjust=False).mean()

        bullish_dict[seg_id] = ema_f > ema_s
        momentum_dict[seg_id] = ema_f - ema_s

    if not earliest_dates:
        return {"error": "Keine Segment-Historie in der Datenbank gefunden."}

    start_str = min(earliest_dates).strftime("%Y-%m-%d")

    spy_px = backtester.fetch_weekly_price("SPY", start_str)
    shy_px = backtester.fetch_weekly_price("SHY", start_str)
    vix_px = backtester.fetch_weekly_price("^VIX", start_str)
    if spy_px.empty or shy_px.empty:
        return {"error": "SPY oder SHY Daten konnten nicht geladen werden."}

    for seg_id, seg_cfg in SEGMENTS.items():
        if seg_id in bullish_dict:
            px = backtester.fetch_weekly_price(seg_cfg["benchmark_etf"], start_str)
            if not px.empty:
                prices_dict[seg_id] = px

    common_idx = spy_px.index
    px_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in prices_dict.items()})
    ret_df = px_df.pct_change()

    spy_aligned = spy_px.reindex(common_idx).ffill()
    spy_sma40 = spy_aligned.rolling(window=40, min_periods=20).mean()  # ~200 Handelstage
    vix_aligned = vix_px.reindex(common_idx).ffill() if not vix_px.empty else pd.Series(0.0, index=common_idx)

    # Parkplatz-Schalter (greift NUR für freies Kapital, nicht für aktive Zykliker)
    park_shy_vix = (vix_aligned > vix_threshold) & (spy_aligned < spy_sma40)
    park_shy_sma = spy_aligned < spy_sma40

    spy_ret = spy_aligned.pct_change().fillna(0.0)
    shy_ret = shy_px.reindex(common_idx).ffill().pct_change().fillna(0.0)

    bull_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in bullish_dict.items() if k in prices_dict})
    mom_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in momentum_dict.items() if k in prices_dict})

    valid_counts = ret_df.notna().sum(axis=1)
    valid_dates = common_idx[valid_counts >= 3]
    if len(valid_dates) < 26:
        return {"error": "Zu wenig gemeinsame Historie über die Sektoren."}

    start_idx = valid_dates[0]
    sim_dates = common_idx[common_idx >= start_idx]

    eq_s1, eq_s2, eq_s3, eq_spy = [100.0], [100.0], [100.0], [100.0]

    for i in range(1, len(sim_dates)):
        dt_prev = sim_dates[i - 1]
        dt_curr = sim_dates[i]

        r_spy = float(spy_ret.at[dt_curr])
        r_shy = float(shy_ret.at[dt_curr])

        # Parkplatz-Rendite für diese Woche (ohne Lookahead-Bias)
        use_shy_vix = bool(park_shy_vix.at[dt_prev]) if pd.notna(park_shy_vix.at[dt_prev]) else False
        use_shy_sma = bool(park_shy_sma.at[dt_prev]) if pd.notna(park_shy_sma.at[dt_prev]) else False

        r_park_smart = r_shy if use_shy_vix else r_spy
        r_park_200dma = r_shy if use_shy_sma else r_spy

        avail = [
            s for s in ret_df.columns
            if pd.notna(ret_df.at[dt_curr, s]) and pd.notna(bull_df.at[dt_prev, s])
        ]
        active = [s for s in avail if bool(bull_df.at[dt_prev, s])]

        # --- Strategie 1 & 3: Alle aktiven BUY/HOLD-Sektoren ---
        if active:
            w_each = min(1.0 / len(active), max_sector_weight)
            w_idle = max(0.0, 1.0 - w_each * len(active))
            active_ret = sum(float(ret_df.at[dt_curr, s]) * w_each for s in active)
            ret_1 = active_ret + w_idle * r_park_smart
            ret_3 = active_ret + w_idle * r_park_200dma
        else:
            ret_1 = r_park_smart
            ret_3 = r_park_200dma

        # --- Strategie 2: Maximal Top-N der aktiven BUY/HOLD-Sektoren ---
        if active:
            active_moms = {
                s: float(mom_df.at[dt_prev, s])
                for s in active
                if pd.notna(mom_df.at[dt_prev, s])
            }
            top_active = sorted(active_moms, key=active_moms.get, reverse=True)[:top_n_active]
            w_each_2 = min(1.0 / len(top_active), max_sector_weight)
            w_idle_2 = max(0.0, 1.0 - w_each_2 * len(top_active))
            ret_2 = sum(float(ret_df.at[dt_curr, s]) * w_each_2 for s in top_active) + w_idle_2 * r_park_smart
        else:
            ret_2 = r_park_smart

        eq_s1.append(eq_s1[-1] * (1.0 + ret_1))
        eq_s2.append(eq_s2[-1] * (1.0 + ret_2))
        eq_s3.append(eq_s3[-1] * (1.0 + ret_3))
        eq_spy.append(eq_spy[-1] * (1.0 + r_spy))

    eq_df = pd.DataFrame({
        "1: Alle Aktiven + Smart Park (VIX+200DMA)": eq_s1,
        f"2: Top-{top_n_active} Aktive + Smart Park": eq_s2,
        "3: Alle Aktiven + 200DMA Park": eq_s3,
        "Benchmark: S&P 500 (SPY)": eq_spy,
    }, index=sim_dates)

    summary = pd.DataFrame([
        _calc_metrics(eq_df["1: Alle Aktiven + Smart Park (VIX+200DMA)"], "1: Alle Aktiven + Smart Park (VIX>25 & 200DMA)"),
        _calc_metrics(eq_df[f"2: Top-{top_n_active} Aktive + Smart Park"], f"2: Top-{top_n_active} Aktive + Smart Park"),
        _calc_metrics(eq_df["3: Alle Aktiven + 200DMA Park"], "3: Alle Aktiven + Reiner 200DMA Park"),
        _calc_metrics(eq_df["Benchmark: S&P 500 (SPY)"], "Benchmark: S&P 500 (SPY)"),
    ]).sort_values(by="CAGR (%/yr)", ascending=False)

    return {"equity": eq_df, "summary": summary}
