"""
notifier.py (Version 3.1 – Fundamental-Checkliste + Zielwert-Legende im BUY-Alert)
- BUY-Alert inkl. Top-10-Aktien (13W-Momentum, 52W-Hoch-Abstand, Fwd P/E, P/B, D/E) + Zielwert-Legende
- ORANGE (Frühwarnung) & SELL (Hard Exit) Alerts
- Sonntags-Digest inkl. Ziel-Allokation (Top-3 Active, max. 35%, Smart Park SPY/SHY)
"""

import html
import os
import pandas as pd
import requests
import yfinance as yf
from config import SEGMENTS, THRESHOLDS
import database as db
import backtester

SECTOR_RESEARCH_FACTORS = {
    "shipping_drybulk": "Orderbook-to-Fleet-Ratio, aktuelle Capesize/Panamax-Spotraten & FFA-Kurve, China Eisenerz-/Kohle-Importe, P/NAV-Bewertung, Cash-Breakeven-Raten und Spot- vs. Charter-Anteil",
    "shipping_tanker": "VLCC/Suezmax/MR-Spotraten, Orderbook-to-Fleet-Ratio, Ton-Mile-Nachfrage & Raffinerie-Auslastung, P/NAV-Bewertung, Verschuldung (LTV) und Spot-Exposure",
    "shipping_lng": "LNG/VLGC-Spotraten, neue US-/Katar-Exportkapazitäten, Orderbook-to-Fleet-Ratio, Gas-Arbitrage-Spreads (Henry Hub vs. TTF/JKM), Charter-Backlog vs. Spot-Exposure und Refinanzierungsrisiken",
    "ind_machinery": "Book-to-Bill-Ratio (> 1.0?), Auftragsbestand (Backlog), Abschluss des Händler-Lagerabbaus (Destocking), ISM New Orders, Operating Leverage und Bruttomargen-Trend",
    "auto_oem": "Absatzzahlen (SAAR), Händler-Lagerbestände (Days' Supply), Rabattdruck vs. Durchschnittspreise (ATPs), EV-CapEx-Belastung vs. Verbrenner-Cashflow und Free-Cashflow-Rendite",
    "agri_fert": "Farmer-Ökonomie (Getreide- vs. Düngerpreise), globale Dünger-Lagerbestände & Exportbeschränkungen (China/Russland), Erdgas-Kostenvorteil der Produzenten und EV/EBITDA",
    "cons_retail": "Same-Store Sales (Comps) Trendwende, Inventar-zu-Umsatz-Verhältnis (saubere Lager -> weniger Rabatte), Bruttomargen-Expansion, Konsumenten-Kreditlage und Nettoverschuldung",
}


def _build_deep_research_prompt(seg_id: str, seg_name: str, score: float, tickers: list[str]) -> str:
    factors = SECTOR_RESEARCH_FACTORS.get(
        seg_id,
        "Angebot/Nachfrage-Bilanz, Kapazitätsauslastung, Margen-Trend, Bewertung (EV/EBITDA, P/B) und Bilanzqualität",
    )
    ticker_str = ", ".join(tickers)
    return (
        f"Mein Makro-Zyklus-System hat heute ein BUY-Signal für das Segment '{seg_name}' "
        f"(Zyklus-Score: {score:.1f}/100) ausgelöst. Führe eine tiefgehende Fundamental- und Zyklus-Analyse durch:\n\n"
        f"1. REALITY-CHECK (Fehlsignal ausschließen): Dreht der fundamentale Zyklus in '{seg_name}' aktuell wirklich nach oben, "
        f"oder handelt es sich um eine Bullenfalle? Prüfe konkret: {factors}.\n\n"
        f"2. PURE-PLAY-SCREENING: Vergleiche diese Kandidaten ({ticker_str}) sowie ggf. 1-2 bessere Pure-Play-Alternativen der Branche. "
        f"Bewerte sie nach: (a) Operating Leverage / Zyklus-Hebel, (b) Bewertung am Zyklusboden (P/B, EV/EBITDA, Fwd P/E), "
        f"(c) Bilanzsicherheit (Net Debt, Liquidität) und (d) aktuellen Aussagen aus den letzten Earnings Calls.\n\n"
        f"3. FAZIT & TOP-PICKS: Gib eine klare Ampel-Einschätzung (Kaufen / Abwarten / Fehlsignal) und nenne die 2 besten "
        f"Aktien mit dem attraktivsten Chance-Risiko-Verhältnis inkl. konkreter Risiken (Bear Case)."
    )

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


def _rank_segment_stocks(stocks: list[str]) -> list[dict]:
    """
    Lädt 13W-Momentum, Abstand zum 52W-Hoch sowie Forward P/E, P/B und Debt/Equity
    für alle hinterlegten Sektor-Aktien via yfinance.
    """
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

            info = yf.Ticker(sym).info or {}
            fwd_pe = info.get("forwardPE")
            pb = info.get("priceToBook")
            dte = info.get("debtToEquity")

            ranked.append({
                "sym": sym,
                "mom_13w": mom_13w,
                "dd_52w": dd_52w,
                "fwd_pe": f"{fwd_pe:.1f}" if isinstance(fwd_pe, (int, float)) and 0 < fwd_pe < 200 else "–",
                "pb": f"{pb:.1f}" if isinstance(pb, (int, float)) and 0 < pb < 50 else "–",
                "dte": f"{dte:.0f}%" if isinstance(dte, (int, float)) and dte >= 0 else "–",
            })
        except Exception:
            continue

    return sorted(ranked, key=lambda x: x["mom_13w"], reverse=True)


def _compute_target_allocation(max_sector_weight: float = 0.35, top_n: int = 3, vix_thresh: float = 25.0) -> dict:
    """
    Berechnet die Ziel-Allokation (in %) für die kommende Woche:
    - Nur aktive Sektoren (EMA 6 > EMA 20), max. 35 % pro Sektor, maximal Top-3 nach Momentum
    - Restliches Kapital in SPY (oder SHY, falls VIX > 25 und SPY < 40W-SMA)
    """
    fast_span = THRESHOLDS.get("regime_fast_ema", 6)
    slow_span = THRESHOLDS.get("regime_slow_ema", 20)

    active_candidates = []
    for seg_id, seg_cfg in SEGMENTS.items():
        hist = db.get_segment_history(seg_id)
        if hist.empty or len(hist) < slow_span:
            continue
        hist = hist.sort_values("date")
        s_tot = hist["s_total"]
        ema_f = float(s_tot.ewm(span=fast_span, adjust=False).mean().iloc[-1])
        ema_s = float(s_tot.ewm(span=slow_span, adjust=False).mean().iloc[-1])
        curr_sig = str(hist["signal"].iloc[-1])

        if ema_f > ema_s:
            active_candidates.append({
                "seg_id": seg_id,
                "etf": seg_cfg["benchmark_etf"],
                "short_name": seg_cfg["short_name"],
                "momentum": ema_f - ema_s,
                "signal": curr_sig,
            })

    active_candidates.sort(key=lambda x: x["momentum"], reverse=True)
    selected = active_candidates[:top_n]

    park_ticker = "SPY"
    park_reason = "SPY > 40W-SMA / VIX normal"
    try:
        spy_px = backtester.fetch_weekly_price("SPY", "2025-01-01")
        vix_px = backtester.fetch_weekly_price("^VIX", "2025-01-01")
        if not spy_px.empty and len(spy_px) >= 20:
            spy_last = float(spy_px.iloc[-1])
            spy_sma40 = float(spy_px.tail(40).mean())
            vix_last = float(vix_px.iloc[-1]) if not vix_px.empty else 0.0
            if vix_last > vix_thresh and spy_last < spy_sma40:
                park_ticker = "SHY"
                park_reason = f"Crash-Park aktiv (VIX {vix_last:.1f} > {vix_thresh:.0f} & SPY < 40W-SMA)"
            else:
                park_reason = f"VIX {vix_last:.1f} | SPY {'<' if spy_last < spy_sma40 else '>='} 40W-SMA"
    except Exception:
        pass

    allocations = []
    used_weight = 0.0
    if selected:
        w_each = min(1.0 / len(selected), max_sector_weight)
        for item in selected:
            pct = round(w_each * 100.0, 1)
            used_weight += pct
            allocations.append({
                "ticker": item["etf"],
                "label": f"{item['short_name']} ({item['signal']})",
                "pct": pct,
            })

    park_pct = round(max(0.0, 100.0 - used_weight), 1)
    if park_pct > 0:
        allocations.append({
            "ticker": park_ticker,
            "label": "Parkplatz",
            "pct": park_pct,
        })

    return {"allocations": allocations, "park_reason": park_reason}


def notify_signal_changes():
    latest_map = db.get_latest_two_segment_signals()

    for seg_id, data in latest_map.items():
        if seg_id not in SEGMENTS:
            continue

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
            top_stocks = _rank_segment_stocks(seg_cfg["stocks"])[:10]
            stock_lines = [
                f"• <b>{s['sym']}</b> | 13W: {s['mom_13w']:+.0f}% | Hoch: {s['dd_52w']:.0f}% | PE: {s['fwd_pe']} | PB: {s['pb']} | D/E: {s['dte']}"
                for s in top_stocks
            ]
            legend = (
                "\n🎯 <b>Gute Werte (Orientierung):</b>\n"
                "• <b>13W:</b> &gt; +5% (Trend dreht, kein fallendes Messer)\n"
                "• <b>Hoch:</b> -15% bis -40% (noch Turnaround-Luft)\n"
                "• <b>PE / PB:</b> Fwd PE &lt; 15 | PB &lt; 1.5 (Shipping/Auto oft &lt; 1.0)\n"
                "• <b>D/E:</b> &lt; 100% (meide &gt; 150% wegen Bilanzrisiko)"
            )
            msg = (
                f"🟢 <b>BUY SIGNAL – {seg_name}</b>\n"
                f"• Score: <b>{curr['s_total']:.1f}</b> (Nachfrage: {curr['s_demand']:.1f})\n"
                f"• Benchmark-ETF: <b>{seg_cfg['benchmark_etf']}</b>\n\n"
                f"📋 <b>Checkliste (sortiert nach 13W-Momentum):</b>\n"
                + ("\n".join(stock_lines) if stock_lines else "  (keine Daten)")
                + "\n"
                + legend
            )
            send_telegram_message(msg)
            dr_prompt = _build_deep_research_prompt(seg_id, seg_cfg["name"], curr["s_total"], seg_cfg["stocks"])
            dr_msg = f"🧠 <b>Gemini Deep Research Prompt (1x tippen zum Kopieren):</b>\n<pre>{html.escape(dr_prompt)}</pre>"
            send_telegram_message(dr_msg)

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
    """Sendet jeden Sonntag den Digest inkl. fertiger Ziel-Allokation (Top-3 Active + Smart Park)."""
    latest_map = db.get_latest_two_segment_signals()
    watchlist = []
    movers = []

    for seg_id, data in latest_map.items():
        if seg_id not in SEGMENTS:
            continue

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

    alloc_info = _compute_target_allocation(max_sector_weight=0.35, top_n=3, vix_thresh=25.0)
    alloc_lines = [
        f"  • <b>{a['pct']:.0f}% {html.escape(a['ticker'])}</b> — {html.escape(a['label'])}"
        for a in alloc_info["allocations"]
    ]

    lines = [
        "📊 <b>Sonntags-Digest &amp; Ziel-Allokation</b>",
        f"• 🟡 Watchlist: {', '.join(watchlist) if watchlist else 'keine'}",
        f"• 🚀 Gewinner: <b>{html.escape(top_up[0])}</b> ({top_up[2]:+.1f} auf {top_up[1]:.1f})",
        f"• 📉 Verlierer: <b>{html.escape(top_down[0])}</b> ({top_down[2]:+.1f} auf {top_down[1]:.1f})",
        f"\n💼 <b>Ziel-Portfolio (Top-3 Active, max. 35%)</b>",
        f"• Park-Check: <i>{html.escape(alloc_info['park_reason'])}</i>",
        *alloc_lines,
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
