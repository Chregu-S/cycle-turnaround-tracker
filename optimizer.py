"""
optimizer.py
1-Klick Auto-Diagnose über alle 10 Sektoren (Benchmark-ETFs).
Testet 5 Strategien gegeneinander und gibt eine klare Empfehlung aus,
ob die Regeln oder der Index selbst geändert werden müssen.
"""

import pandas as pd
from config import SEGMENTS
import database as db
import backtester


def _eval_equity(price: pd.Series, signal_long: pd.Series) -> tuple[float, float, float]:
    """Berechnet (Rendite %, Max Drawdown %, Rendite/Drawdown) ohne Lookahead-Bias."""
    pos = signal_long.shift(1).fillna(False).astype(int)
    ret = price.pct_change().fillna(0.0)
    eq = (1.0 + ret * pos).cumprod() * 100.0

    tot_ret = float(eq.iloc[-1] - 100.0)
    roll_max = eq.cummax()
    max_dd = float(((eq - roll_max) / roll_max).min() * 100.0)
    calmar = round(tot_ret / abs(max_dd), 2) if max_dd < 0 else 0.0
    return round(tot_ret, 1), round(max_dd, 1), calmar


def run_global_diagnosis() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Prüft alle 10 Benchmark-ETFs gegen 5 Strategien + Buy & Hold.
    Rückgabe:
      - detail_df: 1 Zeile pro Sektor mit Gewinner & Klartext-Empfehlung
      - summary_df: Durchschnitt über alle 10 Sektoren (welche 1 Regel global gewinnt)
    """
    detail_rows = []
    strat_scores = {
        "Punkt-Signal (V2.0)": [],
        "Regime 4/13 (Makro)": [],
        "Regime 6/20 (Makro)": [],
        "Regime 6/20 + Preis": [],
        "Nur Preis (20W-EMA)": [],
        "Buy & Hold": [],
    }

    for seg_id, seg_cfg in SEGMENTS.items():
        etf = seg_cfg["benchmark_etf"]
        hist = db.get_segment_history(seg_id)
        if hist.empty:
            continue

        start_str = hist["date"].min().strftime("%Y-%m-%d")
        price = backtester.fetch_weekly_price(etf, start_str)
        if price.empty:
            continue

        df = hist.copy().set_index("date")
        df["price"] = price.reindex(df.index).ffill()
        df = df.dropna(subset=["price"])
        if len(df) < 30:
            continue

        # 1. Aktuelles Punkt-Signal (V2.0)
        pt = backtester.run_backtest(hist, etf, use_double_lock=True, trailing_stop_pct=0.15)
        if "error" in pt:
            pt_ret, pt_dd, pt_cal = 0.0, 0.0, 0.0
        else:
            pt_ret = pt["metrics"]["strat_return"]
            pt_dd = pt["metrics"]["max_dd_strat"]
            pt_cal = round(pt_ret / abs(pt_dd), 2) if pt_dd < 0 else 0.0

        # 2. Geglättete Makro-Regime & Preis-Benchmarks
        s_ema4 = df["s_total"].ewm(span=4, adjust=False).mean()
        s_ema6 = df["s_total"].ewm(span=6, adjust=False).mean()
        s_ema13 = df["s_total"].ewm(span=13, adjust=False).mean()
        s_ema20 = df["s_total"].ewm(span=20, adjust=False).mean()
        p_ema10 = df["price"].ewm(span=10, adjust=False).mean()
        p_ema20 = df["price"].ewm(span=20, adjust=False).mean()

        r4_13 = _eval_equity(df["price"], s_ema4 > s_ema13)
        r6_20 = _eval_equity(df["price"], s_ema6 > s_ema20)
        r6_20_p = _eval_equity(df["price"], (s_ema6 > s_ema20) & (df["price"] > p_ema10))
        p_only = _eval_equity(df["price"], df["price"] > p_ema20)
        bh = _eval_equity(df["price"], pd.Series(True, index=df.index))

        results = {
            "Punkt-Signal (V2.0)": (pt_ret, pt_dd, pt_cal),
            "Regime 4/13 (Makro)": r4_13,
            "Regime 6/20 (Makro)": r6_20,
            "Regime 6/20 + Preis": r6_20_p,
            "Nur Preis (20W-EMA)": p_only,
            "Buy & Hold": bh,
        }

        for k, v in results.items():
            strat_scores[k].append(v)

        # Beste aktive Strategie nach Rendite/Drawdown (ohne Buy & Hold)
        active = {k: v for k, v in results.items() if k != "Buy & Hold"}
        best_name = max(active, key=lambda k: active[k][2])
        best_ret, best_dd, best_cal = active[best_name]

        # Klartext-Diagnose
        if best_name == "Nur Preis (20W-EMA)":
            verdict = "⚠️ Makro-Index zu langsam -> Preis-Trend schlägt Zyklus"
        elif best_cal > bh[2]:
            verdict = f"✅ {best_name} schlägt B&H (besserer Drawdown-Schutz)"
        else:
            verdict = f"ℹ️ B&H stärker, beste Alternative: {best_name}"

        detail_rows.append({
            "Sektor": seg_cfg["short_name"],
            "ETF": etf,
            "B&H Rendite": f"{bh[0]:+.1f}% (DD {bh[1]:.0f}%)",
            "V2.0 Punkt": f"{pt_ret:+.1f}%",
            "Regime 6/20": f"{r6_20[0]:+.1f}%",
            "Nur Preis": f"{p_only[0]:+.1f}%",
            "Gewinner (Aktiv)": best_name,
            "Diagnose": verdict,
        })

    # Globaler Durchschnitt über alle 10 Sektoren
    summary_rows = []
    for name, vals in strat_scores.items():
        if not vals:
            continue
        avg_ret = round(sum(v[0] for v in vals) / len(vals), 1)
        avg_dd = round(sum(v[1] for v in vals) / len(vals), 1)
        avg_cal = round(sum(v[2] for v in vals) / len(vals), 2)
        summary_rows.append({
            "Strategie": name,
            "Ø Rendite (10 Sektoren)": avg_ret,
            "Ø Max Drawdown (%)": avg_dd,
            "Ø Rendite / Drawdown": avg_cal,
        })

    summary_df = pd.DataFrame(summary_rows).sort_values(by="Ø Rendite / Drawdown", ascending=False)
    return pd.DataFrame(detail_rows), summary_df
