"""
analyzer.py
Quant-Lab für den Cycle Turnaround Tracker.
Führt 3 wissenschaftliche Diagnosen pro Segment & Wertpapier durch:
1. Lead/Lag Cross-Correlation (läuft der Zyklus-Score dem Kurs voraus oder hinterher?)
2. Forward-Return-Matrix (welche Score-Zonen bringen historisch wirklich Rendite?)
3. Strategie-Vergleich: Geglättetes Zyklus-Regime (EMA-Cross) vs. Punkt-Signal vs. Buy & Hold
"""

import numpy as np
import pandas as pd
import backtester


def compute_lead_lag(hist_df: pd.DataFrame, price: pd.Series, max_lag: int = 26) -> dict:
    """
    Berechnet die Kreuzkorrelation zwischen Zyklus-Score und Aktienkurs
    für Verschiebungen von -max_lag bis +max_lag Wochen.
    - Lag > 0: Score läuft dem Kurs voraus (Frühindikator)
    - Lag < 0: Score läuft dem Kurs hinterher (Nachläufer)
    """
    df = hist_df.copy().set_index("date")[["s_total"]]
    df["price"] = price.reindex(df.index).ffill()
    df = df.dropna()

    if len(df) < 40:
        return {"error": "Zu wenig Daten für Lead/Lag-Analyse."}

    lags = list(range(-max_lag, max_lag + 1))
    corrs = []
    for lag in lags:
        # shift(+lag) prüft: Korreliert der Score von vor 'lag' Wochen mit dem heutigen Kurs?
        c = df["s_total"].shift(lag).corr(df["price"])
        corrs.append(float(c) if pd.notna(c) else 0.0)

    corr_df = pd.DataFrame({"lag_weeks": lags, "correlation": corrs})
    best_row = corr_df.loc[corr_df["correlation"].idxmax()]

    return {
        "df": corr_df,
        "best_lag": int(best_row["lag_weeks"]),
        "best_corr": round(float(best_row["correlation"]), 3),
    }


def compute_forward_return_matrix(
    hist_df: pd.DataFrame, price: pd.Series, horizon_weeks: int = 26
) -> dict:
    """
    Teilt die Historie in 4 Score-Zonen (0-25, 25-50, 50-75, 75-100) und
    2 Trend-Zustände (Steigend vs. Fallend relativ zum 8W-EMA des Scores).
    Berechnet pro Zelle die durchschnittliche Forward-Rendite (%) über 'horizon_weeks'.
    """
    df = hist_df.copy().set_index("date")[["s_total"]]
    df["price"] = price.reindex(df.index).ffill()
    df = df.dropna()

    if len(df) < horizon_weeks + 20:
        return {"error": "Zu wenig Historie für den gewählten Forward-Horizont."}

    df["score_ema"] = df["s_total"].ewm(span=8, adjust=False).mean()
    df["trend"] = np.where(df["s_total"] >= df["score_ema"], "Steigend", "Fallend")
    df["fwd_ret"] = ((df["price"].shift(-horizon_weeks) / df["price"]) - 1.0) * 100.0

    bins = [0, 25, 50, 75, 100.01]
    labels = ["0–25 (Boden)", "25–50 (Früh)", "50–75 (Mid)", "75–100 (Hoch)"]
    df["bucket"] = pd.cut(df["s_total"], bins=bins, labels=labels, include_lowest=True)

    valid = df.dropna(subset=["fwd_ret", "bucket"])

    mean_piv = valid.pivot_table(
        index="trend", columns="bucket", values="fwd_ret", aggfunc="mean", observed=False
    ).reindex(index=["Steigend", "Fallend"], columns=labels)

    count_piv = valid.pivot_table(
        index="trend", columns="bucket", values="fwd_ret", aggfunc="count", observed=False
    ).reindex(index=["Steigend", "Fallend"], columns=labels).fillna(0).astype(int)

    return {"mean": mean_piv, "count": count_piv}


def compare_strategies(
    hist_df: pd.DataFrame,
    ticker: str,
    fast_ema: int = 4,
    slow_ema: int = 13,
    use_price_filter: bool = True,
    trailing_stop_pct: float = 0.15,
) -> dict:
    """
    Vergleicht 3 Strategien direkt gegeneinander:
    1. Buy & Hold
    2. Bisheriges Punkt-Signal (aus backtester.py)
    3. Geglättetes Zyklus-Regime (Score Fast-EMA > Slow-EMA -> LONG, sonst FLAT)
    """
    if hist_df.empty:
        return {"error": "Keine Segment-Historie vorhanden."}

    start_str = hist_df["date"].min().strftime("%Y-%m-%d")
    price = backtester.fetch_weekly_price(ticker, start_str)
    if price.empty:
        return {"error": f"Keine Kursdaten für {ticker} gefunden."}

    # 1. Bisheriges Punkt-Signal
    pt_res = backtester.run_backtest(
        hist_df,
        ticker,
        use_double_lock=use_price_filter,
        ema_weeks=10,
        trailing_stop_pct=trailing_stop_pct,
    )
    if "error" in pt_res:
        return pt_res

    df = pt_res["df"].copy()

    # 2. Geglättetes Zyklus-Regime berechnen
    df["score_fast"] = df["s_total"].ewm(span=fast_ema, adjust=False).mean()
    df["score_slow"] = df["s_total"].ewm(span=slow_ema, adjust=False).mean()
    df["price_ema10"] = df["price"].ewm(span=10, adjust=False).mean()

    regime_long = df["score_fast"] > df["score_slow"]
    if use_price_filter:
        regime_long = regime_long & (df["price"] > df["price_ema10"])

    # Position gilt ab der Folgewoche (kein Lookahead-Bias)
    pos = regime_long.shift(1).fillna(False).astype(int)
    weekly_ret = df["price"].pct_change().fillna(0.0)
    df["regime_equity"] = (1.0 + weekly_ret * pos).cumprod() * 100.0

    # Kennzahlen für alle 3 Strategien berechnen
    def _calc_stats(eq_series: pd.Series, time_in_mkt: float, name: str) -> dict:
        tot_ret = float(eq_series.iloc[-1] - 100.0)
        roll_max = eq_series.cummax()
        max_dd = float(((eq_series - roll_max) / roll_max).min() * 100.0)
        calmar = round(tot_ret / abs(max_dd), 2) if max_dd < 0 else 0.0
        return {
            "Strategie": name,
            "Gesamtrendite (%)": round(tot_ret, 1),
            "Max Drawdown (%)": round(max_dd, 1),
            "Rendite / Drawdown": calmar,
            "Investiert (%)": round(time_in_mkt, 1),
        }

    regime_invested_pct = float(pos.mean() * 100.0)
    # Investierte Zeit der Punkt-Strategie schätzen (Wochen mit Kapitaländerung)
    pt_invested_pct = float((df["strategy_equity"].pct_change().fillna(0) != 0).mean() * 100.0)

    summary = pd.DataFrame([
        _calc_stats(df["regime_equity"], regime_invested_pct, f"Geglättetes Regime (EMA {fast_ema}/{slow_ema})"),
        _calc_stats(df["strategy_equity"], pt_invested_pct, "Punkt-Signal (V2.0)"),
        _calc_stats(df["bh_equity"], 100.0, f"Buy & Hold ({ticker})"),
    ])

    return {
        "df": df,
        "price": price,
        "summary": summary,
    }
