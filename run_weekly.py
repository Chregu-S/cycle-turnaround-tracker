"""
run_weekly.py
Hauptskript für das wöchentliche Update des Cycle Turnaround Trackers.
Ablauf:
1. Datenbank initialisieren (falls noch nicht vorhanden)
2. Alle 60 Indikatoren abrufen & in SQLite speichern (inkl. 6-Jahres-Backfill beim 1. Lauf)
3. 5-Jahres-Perzentile, Scores & Ampel-Zustände berechnen
4. Telegram-Alerts bei neuen GRÜN-Signalen oder Daten-Warnungen versenden
5. Lauf im Log protokollieren
"""

import traceback
from dotenv import load_dotenv

import database as db
import fetcher
import engine
import notifier


def main():
    # Lädt lokale Umgebungsvariablen aus einer .env-Datei (falls vorhanden)
    load_dotenv()

    print("=== Cycle Turnaround Tracker: Wöchentliches Update ===")
    db.init_db()

    try:
        # 1. Daten abrufen (inkl. Fehlertoleranz & Fallback)
        warnings = fetcher.fetch_all_indicators()

        # 2. Scoring & Ampel-State-Machine berechnen
        engine.run_scoring_engine()

        # 3. Telegram-Benachrichtigungen prüfen & versenden
        notifier.notify_new_green_signals()
        if warnings:
            notifier.notify_warnings(warnings)

        # 4. Erfolg protokollieren
        status = "WARNUNG" if warnings else "OK"
        msg = f"Update abgeschlossen mit {len(warnings)} Warnung(en)."
        db.log_run(status, msg)
        print(f"=== Fertig ({status}): {msg} ===")

    except Exception as e:
        err_msg = f"Kritischer Fehler im wöchentlichen Lauf: {e}"
        print(err_msg)
        traceback.print_exc()
        db.log_run("FEHLER", err_msg)
        notifier.send_telegram_message(f"🚨 <b>Cycle Tracker – Kritischer Fehler</b>\n\n{err_msg}")
        raise


if __name__ == "__main__":
    main()