"""
notifier.py
Sendet Telegram-Push-Nachrichten über die Telegram Bot API:
1. Bei einem echten Statuswechsel eines Segments auf 'GRUEN' (Entry-Signal).
2. Bei Datenfehlern/Fallbacks während des wöchentlichen Laufs.
"""

import os
import requests
from config import SEGMENTS
import database as db


def send_telegram_message(text: str) -> bool:
    """Sendet eine Nachricht an den konfigurierten Telegram-Chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[INFO] TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID nicht gesetzt. Überspringe Push.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("[OK] Telegram-Nachricht gesendet.")
        return True
    except Exception as e:
        print(f"[FEHLER] Telegram-Versand fehlgeschlagen: {e}")
        return False


def notify_new_green_signals():
    """
    Prüft alle 10 Segmente auf einen Statuswechsel auf 'GRUEN'
    (d. h. aktuell GRUEN, Vorwoche != GRUEN) und sendet eine Push-Nachricht.
    """
    latest_map = db.get_latest_two_segment_signals()
    new_greens = []

    for seg_id, data in latest_map.items():
        curr = data.get("current")
        prev = data.get("previous")
        if not curr:
            continue

        curr_sig = curr.get("signal")
        prev_sig = prev.get("signal") if prev else None

        if curr_sig == "GRUEN" and prev_sig != "GRUEN":
            seg_name = SEGMENTS[seg_id]["name"]
            new_greens.append((seg_name, curr, prev_sig))

    if not new_greens:
        print("[INFO] Keine neuen GRÜN-Signale diese Woche.")
        return

    lines = ["🟢 <b>CYCLE TURNAROUND ALERT – NEUES ENTRY-SIGNAL</b>\n"]
    for seg_name, curr, prev_sig in new_greens:
        lines.append(
            f"<b>{seg_name}</b>\n"
            f"• Wechsel: {prev_sig or 'NEU'} ➡️ <b>GRÜN</b>\n"
            f"• Gesamt-Score: <b>{curr['s_total']:.1f}</b> / 100\n"
            f"• Nachfrage: {curr['s_demand']:.1f} | Kapazität: {curr['s_capacity']:.1f} | Preis: {curr['s_price']:.1f}\n"
            f"• Stand: {curr['date']}\n"
        )

    send_telegram_message("\n".join(lines))


def notify_warnings(warnings: list[str]):
    """Sendet eine kompakte Warnmeldung, falls einzelne APIs/Scraper ausgefallen sind."""
    if not warnings:
        return

    max_show = 8
    shown = warnings[:max_show]
    extra = len(warnings) - len(shown)

    lines = [
        "⚠️ <b>Cycle Tracker – Daten-Warnungen (Fallback aktiv)</b>\n",
        f"Bei {len(warnings)} Indikator(en) wurde der letzte bekannte Wert genutzt:\n",
    ]
    for w in shown:
        lines.append(f"• {w}")
    if extra > 0:
        lines.append(f"\n... und {extra} weitere Warnungen.")

    send_telegram_message("\n".join(lines))