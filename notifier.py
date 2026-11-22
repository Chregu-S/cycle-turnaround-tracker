"""
notifier.py (Version 2.0)
- BUY-Alert inkl. automatischem Stock-Picker (Top-3-Aktien nach 13W-Momentum)
- ORANGE (Frühwarnung) & SELL (Hard Exit) Alerts
- Kompakter Sonntags-Digest (Watchlist GELB + Top-Mover)
- Sicherer HTML-Escape für Daten-Warnungen
"""

import html
import os
import requests
import yfinance as yf
from config import SEGMENTS
import database as db


def send_telegram_message(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[INFO] Telegram-Secrets fehlen. Überspringe Push.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("[OK] Telegram-Nachricht gesendet.")
        return True
    except Exception as e:
        print(f"[FEHLER] Telegram-Versand fehlgeschlagen: {e}")
        return False


def _rank_segment_stocks(stocks: list[str]) -> list[tuple[str, float, float]]:
    """Rankt die Aktien eines Segments nach 13-Wochen-Momentum (%) & Abstand zum 52W-Hoch."""
    ranked = []
    for sym in stocks:
        try:
            df = yf.download(sym, period="1y", progress=False, auto_adjust=True, threads=False)
            if df is None or df.empty:
                continue
            close = df["Close"].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
            close = close.dropna()
            if len(close) < 65:
                continue
            curr = float(close.iloc[-1])
            mom_13w = ((curr / float(close.iloc[-65])) - 1.0) * 100.0
            dd_52w = ((curr / float(close.max())) - 1.0) * 100.0
            ranked.append((sym, mom_13w, dd_52w))
        except Exception:
            continue
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def notify_signal_changes():
    """Sendet Alerts bei Statuswechsel auf BUY, ORANGE oder SELL."""
    latest_map = db.get_latest_two_segment_signals()

    for seg_id, data in latest_map.items():
        curr = data.get("current")
        prev = data.get("previous")
        if not curr:
            continue

        c_sig = curr["signal"]
        p_sig = prev["signal"] if prev else None
        if c_sig == p_sig:
            continue

        seg_cfg = SEGMENTS[seg_id]
        seg_name = html.escape(seg_cfg["name"])

        if c_sig == "BUY":
            top_stocks = _rank_segment_stocks(seg_cfg["stocks"])[:3]
            stock_lines = [f"  • <b>{s}</b>: {m:+.1f}% (13W) | {dd:.1f}% v. 52W-Hoch" for s, m, dd in top_stocks]
            msg = (
                f"🟢 <b>BUY SIGNAL – {seg_name}</b>\n"
                f"• Score: <b>{curr['s_total']:.1f}</b> (Nachfrage: {curr['s_demand']:.1f})\n"
                f"• Benchmark-ETF: <b>{seg_cfg['benchmark_etf']}</b>\n"
                f"• Top-Aktien (Relative Stärke):\n" + ("\n".join(stock_lines) if stock_lines else "  (keine Daten)")
            )
            send_telegram_message(msg)

        elif c_sig == "ORANGE":
            msg = (
                f"🟠 <b>FRÜHWARNUNG (TEILVERKAUF) – {seg_name}</b>\n"
                f"• Score überhitzt ({curr['s_total']:.1f}) &amp; Nachfrage dreht ab ({curr['s_demand']:.1f}).\n"
                f"• Empfehlung: Teilgewinne sichern / Trailing-Stop eng ziehen."
            )
            send_telegram_message(msg)

        elif c_sig == "SELL":
            msg = (
                f"🔴 <b>SELL SIGNAL (HARD EXIT) – {seg_name}</b>\n"
                f"• Zyklus-Bruch bestätigt! Score: <b>{curr['s_total']:.1f}</b>.\n"
                f"• Empfehlung: Offene Positionen in diesem Segment schließen."
            )
            send_telegram_message(msg)


def notify_weekly_digest():
    """Sendet jeden Sonntag eine kompakte 5-Zeilen-Übersicht (Watchlist & Mover)."""
    latest_map = db.get_latest_two_segment_signals()
    watchlist = []
    movers = []

    for seg_id, data in latest_map.items():
        curr = data.get("current")
        prev = data.get("previous")
        if not curr:
            continue
        name = SEGMENTS[seg_id]["short_name"]
        delta = (curr["s_total"] - prev["s_total"]) if prev else 0.0
        movers.append((name, curr["s_total"], delta, curr["signal"]))
        if curr["signal"] == "GELB":
            watchlist.append(f"{name} ({curr['s_total']:.1f})")

    if not movers:
        return

    movers.sort(key=lambda x: x[2], reverse=True)
    top_up = movers[0]
    top_down = movers[-1]

    lines = [
        "📊 <b>Sonntags-Digest – Cycle Tracker</b>",
        f"• 🟡 Watchlist (kurz vor BUY): {', '.join(watchlist) if watchlist else 'keine'}",
        f"• 🚀 Wochengewinner: <b>{top_up[0]}</b> ({top_up[2]:+.1f} auf {top_up[1]:.1f})",
        f"• 📉 Wochenverlierer: <b>{top_down[0]}</b> ({top_down[2]:+.1f} auf {top_down[1]:.1f})",
    ]
    send_telegram_message("\n".join(lines))


def notify_warnings(warnings: list[str]):
    if not warnings:
        return
    shown = [f"• {html.escape(w)}" for w in warnings[:8]]
    lines = [
        "⚠️ <b>Cycle Tracker – Daten-Warnungen</b>",
        f"{len(warnings)} Indikator(en) im Fallback:\n",
        *shown,
    ]
    send_telegram_message("\n".join(lines))
