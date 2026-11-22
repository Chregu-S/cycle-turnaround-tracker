"""
backtester.py
Backtest-Engine für den Cycle Turnaround Tracker.
Legt echte ETF-/Aktienkurse über die Makro-Signale und testet:
- Double-Lock (Einstieg nur, wenn Kurs > 10-Wochen-EMA)
- Trailing-Stop (z. B. 15 % unter Zyklus-Hoch)
- Vergleich: Strategie vs. Buy & Hold
"""

import numpy as np
import pandas as pd
import yfinance as yf


def fetch_weekly_price(ticker: str, start_date: str) -> pd.Series:
    """Lädt wöchentliche Schlusskurse (Sonntag) für ein Wertpapier."""
    padded_start = (pd.Timestamp(start_date) - pd.DateOffset(weeks=15)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=padded_start, progress=False, auto_adjust=True, threads=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)

    close = df["Close"].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.resample("W-SUN").last().ffill().dropna()


def run_backtest(
    hist_df: pd.DataFrame,
    ticker: str,
    use_double_lock: bool = True,
    ema_weeks: int = 10,
    trailing_stop_pct: float = 0.15,
) -> dict:
    """
    Führt einen wöchentlichen Backtest für einen Ticker auf Basis der
    Segment-Signale aus.
    """
    if hist_df.empty:
        return {"error": "Keine Segment-Historie vorhanden."}

    start_str = hist_df["date"].min().strftime("%Y-%m-%d")
    price = fetch_weekly_price(ticker, start_str)
    if price.empty:
        return {"error": f"Keine Kursdaten für {ticker} gefunden."}

    ema = price.ewm(span=ema_weeks, adjust=False).mean()

    df = hist_df.copy().set_index("date")
    df["price"] = price.reindex(df.index).ffill()
    df["ema"] = ema.reindex(df.index).ffill()
    df = df.dropna(subset=["price"])

    if len(df) < 10:
        return {"error": f"Zu wenig gemeinsame Historie für {ticker}."}

    in_pos = False
    entry_price = 0.0
    entry_date = None
    peak_price = 0.0

    equity = [100.0]
    trades = []
    buy_points = []
    sell_points = []

    prices = df["price"].values
    emas = df["ema"].values
    signals = df["signal"].values
    dates = df.index

    for i in range(1, len(df)):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        sig = signals[i]

        # Kapital fortschreiben, wenn investiert
        if in_pos:
            ret = (p_curr / p_prev) - 1.0
            equity.append(equity[-1] * (1.0 + ret))
            peak_price = max(peak_price, p_curr)
        else:
            equity.append(equity[-1])

        # 1. Einstieg prüfen
        if not in_pos and sig == "BUY":
            tech_ok = (p_curr > emas[i]) if use_double_lock else True
            if tech_ok:
                in_pos = True
                entry_price = p_curr
                entry_date = dates[i]
                peak_price = p_curr
                buy_points.append((dates[i], p_curr, "BUY"))

        # 2. Ausstieg prüfen (Makro-SELL ODER Trailing-Stop)
        elif in_pos:
            stop_hit = (trailing_stop_pct > 0) and (p_curr <= peak_price * (1.0 - trailing_stop_pct))
            macro_sell = sig == "SELL"

            if macro_sell or stop_hit:
                reason = "Trailing-Stop" if (stop_hit and not macro_sell) else "Makro-SELL"
                trade_ret = ((p_curr / entry_price) - 1.0) * 100.0
                hold_wks = max(1, int((dates[i] - entry_date).days / 7))
                trades.append({
                    "Einstieg": entry_date.strftime("%Y-%m-%d"),
                    "Ausstieg": dates[i].strftime("%Y-%m-%d"),
                    "Kaufkurs": round(entry_price, 2),
                    "Verkaufskurs": round(p_curr, 2),
                    "Rendite (%)": round(trade_ret, 1),
                    "Haltedauer (Wochen)": hold_wks,
                    "Grund": reason,
                })
                sell_points.append((dates[i], p_curr, reason))
                in_pos = False

    # Offene Position am Ende dokumentieren
    if in_pos:
        trade_ret = ((prices[-1] / entry_price) - 1.0) * 100.0
        hold_wks = max(1, int((dates[-1] - entry_date).days / 7))
        trades.append({
            "Einstieg": entry_date.strftime("%Y-%m-%d"),
            "Ausstieg": "OFFEN",
            "Kaufkurs": round(entry_price, 2),
            "Verkaufskurs": round(prices[-1], 2),
            "Rendite (%)": round(trade_ret, 1),
            "Haltedauer (Wochen)": hold_wks,
            "Grund": "Aktuell LONG",
        })

    df["strategy_equity"] = equity
    df["bh_equity"] = (df["price"] / df["price"].iloc[0]) * 100.0

    # Kennzahlen berechnen
    strat_ret = df["strategy_equity"].iloc[-1] - 100.0
    bh_ret = df["bh_equity"].iloc[-1] - 100.0

    roll_max_strat = df["strategy_equity"].cummax()
    max_dd_strat = ((df["strategy_equity"] - roll_max_strat) / roll_max_strat).min() * 100.0

    roll_max_bh = df["bh_equity"].cummax()
    max_dd_bh = ((df["bh_equity"] - roll_max_bh) / roll_max_bh).min() * 100.0

    closed_trades = [t for t in trades if t["Ausstieg"] != "OFFEN"]
    wins = [t for t in closed_trades if t["Rendite (%)"] > 0]
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0

    return {
        "df": df.reset_index(),
        "trades": pd.DataFrame(trades),
        "buy_points": buy_points,
        "sell_points": sell_points,
        "metrics": {
            "strat_return": round(strat_ret, 1),
            "bh_return": round(bh_ret, 1),
            "max_dd_strat": round(max_dd_strat, 1),
            "max_dd_bh": round(max_dd_bh, 1),
            "num_trades": len(trades),
            "win_rate": round(win_rate, 1),
        },
    }
