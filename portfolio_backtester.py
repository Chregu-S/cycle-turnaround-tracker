"""
portfolio_backtester.py
Multi-sector portfolio backtester comparing 3 tactical scenarios against SPY:
- Scenario A: Active BUY/HOLD sectors (Regime 6/20), idle cash in Treasuries (SHY)
- Scenario B: Active BUY/HOLD sectors (Regime 6/20), idle cash in S&P 500 (SPY)
- Scenario C: Always invested in the Top 2 sectors by cycle momentum (EMA 6 - EMA 20)
- Benchmark:  100% Buy & Hold S&P 500 (SPY)
"""

import numpy as np
import pandas as pd
from config import SEGMENTS, THRESHOLDS
import database as db
import backtester


def _calc_metrics(eq: pd.Series, name: str) -> dict:
    """Calculates Total Return, CAGR, Max Drawdown, and CAGR/MaxDD ratio."""
    tot_ret = (float(eq.iloc[-1]) / float(eq.iloc[0]) - 1.0) * 100.0
    years = max(0.5, (eq.index[-1] - eq.index[0]).days / 365.25)
    cagr = ((float(eq.iloc[-1]) / float(eq.iloc[0])) ** (1.0 / years) - 1.0) * 100.0

    roll_max = eq.cummax()
    max_dd = float(((eq - roll_max) / roll_max).min() * 100.0)
    calmar = round(cagr / abs(max_dd), 2) if max_dd < 0 else 0.0

    return {
        "Strategy": name,
        "Total Return (%)": round(tot_ret, 1),
        "CAGR (%/yr)": round(cagr, 1),
        "Max Drawdown (%)": round(max_dd, 1),
        "CAGR / Max DD": calmar,
    }


def run_portfolio_backtest(max_sector_weight: float = 0.33) -> dict:
    """Runs the multi-sector portfolio simulation across all active SEGMENTS."""
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
        return {"error": "No segment history found in database."}

    start_str = min(earliest_dates).strftime("%Y-%m-%d")

    spy_px = backtester.fetch_weekly_price("SPY", start_str)
    shy_px = backtester.fetch_weekly_price("SHY", start_str)
    if spy_px.empty or shy_px.empty:
        return {"error": "Could not load SPY or SHY benchmark data."}

    for seg_id, seg_cfg in SEGMENTS.items():
        if seg_id in bullish_dict:
            px = backtester.fetch_weekly_price(seg_cfg["benchmark_etf"], start_str)
            if not px.empty:
                prices_dict[seg_id] = px

    common_idx = spy_px.index
    px_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in prices_dict.items()})
    ret_df = px_df.pct_change()

    spy_ret = spy_px.reindex(common_idx).ffill().pct_change().fillna(0.0)
    shy_ret = shy_px.reindex(common_idx).ffill().pct_change().fillna(0.0)

    bull_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in bullish_dict.items() if k in prices_dict})
    mom_df = pd.DataFrame({k: v.reindex(common_idx).ffill() for k, v in momentum_dict.items() if k in prices_dict})

    valid_counts = ret_df.notna().sum(axis=1)
    valid_dates = common_idx[valid_counts >= 3]
    if len(valid_dates) < 26:
        return {"error": "Not enough overlapping history across sectors."}

    start_idx = valid_dates[0]
    sim_dates = common_idx[common_idx >= start_idx]

    eq_a = [100.0]
    eq_b = [100.0]
    eq_c = [100.0]
    eq_spy = [100.0]

    for i in range(1, len(sim_dates)):
        dt_prev = sim_dates[i - 1]
        dt_curr = sim_dates[i]

        avail = [
            s for s in ret_df.columns
            if pd.notna(ret_df.at[dt_curr, s]) and pd.notna(bull_df.at[dt_prev, s])
        ]
        active = [s for s in avail if bool(bull_df.at[dt_prev, s])]

        r_spy = float(spy_ret.at[dt_curr])
        r_shy = float(shy_ret.at[dt_curr])

        # Scenario A & B: Active BUY/HOLD sectors
        if active:
            w_each = min(1.0 / len(active), max_sector_weight)
            w_idle = max(0.0, 1.0 - w_each * len(active))
            active_ret = sum(float(ret_df.at[dt_curr, s]) * w_each for s in active)
            ret_a = active_ret + w_idle * r_shy
            ret_b = active_ret + w_idle * r_spy
        else:
            ret_a = r_shy
            ret_b = r_spy

        # Scenario C: Always Top 2 by Cycle Momentum (EMA 6 - EMA 20)
        if len(avail) >= 2:
            moms = {s: float(mom_df.at[dt_prev, s]) for s in avail if pd.notna(mom_df.at[dt_prev, s])}
            top2 = sorted(moms, key=moms.get, reverse=True)[:2]
            ret_c = float(np.mean([float(ret_df.at[dt_curr, s]) for s in top2]))
        elif avail:
            ret_c = float(ret_df.at[dt_curr, avail[0]])
        else:
            ret_c = r_shy

        eq_a.append(eq_a[-1] * (1.0 + ret_a))
        eq_b.append(eq_b[-1] * (1.0 + ret_b))
        eq_c.append(eq_c[-1] * (1.0 + ret_c))
        eq_spy.append(eq_spy[-1] * (1.0 + r_spy))

    eq_df = pd.DataFrame({
        "Active -> Treasuries (SHY)": eq_a,
        "Active -> S&P 500 (SPY)": eq_b,
        "Always Top 2 Sectors": eq_c,
        "S&P 500 Benchmark (SPY)": eq_spy,
    }, index=sim_dates)

    summary = pd.DataFrame([
        _calc_metrics(eq_df["Active -> Treasuries (SHY)"], "A: Active Sectors -> Treasuries (SHY)"),
        _calc_metrics(eq_df["Active -> S&P 500 (SPY)"], "B: Active Sectors -> S&P 500 (SPY)"),
        _calc_metrics(eq_df["Always Top 2 Sectors"], "C: Always Top 2 Sectors"),
        _calc_metrics(eq_df["S&P 500 Benchmark (SPY)"], "Benchmark: S&P 500 (SPY)"),
    ]).sort_values(by="CAGR (%/yr)", ascending=False)

    return {"equity": eq_df, "summary": summary}
