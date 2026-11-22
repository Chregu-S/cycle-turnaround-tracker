"""
database.py
Verwaltet die lokale SQLite-Datenbank (cycle_data.db).
Speichert Rohdaten, berechnete Perzentile, Segment-Scores und Update-Logs.
"""

import sqlite3
from datetime import datetime, timezone
import pandas as pd
from config import DB_PATH


def get_connection():
    """Öffnet eine Verbindung zur SQLite-Datenbank."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Erstellt alle benötigten Tabellen, falls sie noch nicht existieren."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Rohdaten aller 60 Indikatoren (wöchentliches Raster, sonntags)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_indicators (
                date TEXT NOT NULL,
                indicator_id TEXT NOT NULL,
                raw_value REAL,
                status TEXT DEFAULT 'OK',
                updated_at TEXT,
                PRIMARY KEY (date, indicator_id)
            )
        """)

        # 2. Normalisierte Perzentil-Scores je Einzelindikator (für Detail-Tabelle)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicator_scores (
                date TEXT NOT NULL,
                indicator_id TEXT NOT NULL,
                segment_id TEXT NOT NULL,
                raw_value REAL,
                percentile REAL,
                status TEXT DEFAULT 'OK',
                PRIMARY KEY (date, indicator_id)
            )
        """)

        # 3. Aggregierte Segment-Scores & Ampel-Zustand
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segment_scores (
                date TEXT NOT NULL,
                segment_id TEXT NOT NULL,
                s_demand REAL,
                s_capacity REAL,
                s_price REAL,
                s_total REAL,
                signal TEXT,
                PRIMARY KEY (date, segment_id)
            )
        """)

        # 4. Protokoll der wöchentlichen Läufe (für Monitoring & Dashboard-Datum)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT
            )
        """)

        conn.commit()


# ==============================================================================
# SCHREIB-FUNKTIONEN
# ==============================================================================

def save_raw_series(indicator_id: str, series: pd.Series, status: str = "OK"):
    """
    Speichert eine wöchentliche Zeitreihe (pd.Series mit DatetimeIndex)
    in der Tabelle raw_indicators. Bestehende Werte werden aktualisiert.
    """
    if series is None or series.empty:
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = []
    for dt, val in series.dropna().items():
        date_str = pd.Timestamp(dt).strftime("%Y-%m-%d")
        rows.append((date_str, indicator_id, float(val), status, now_str))

    if not rows:
        return

    with get_connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO raw_indicators
            (date, indicator_id, raw_value, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


def save_indicator_scores(df: pd.DataFrame):
    """
    Speichert berechnete Perzentil-Scores in indicator_scores.
    Erwartete Spalten: ['date', 'indicator_id', 'segment_id', 'raw_value', 'percentile', 'status']
    """
    if df.empty:
        return

    rows = [
        (
            str(r["date"]),
            str(r["indicator_id"]),
            str(r["segment_id"]),
            float(r["raw_value"]) if pd.notna(r["raw_value"]) else None,
            float(r["percentile"]) if pd.notna(r["percentile"]) else None,
            str(r["status"]),
        )
        for _, r in df.iterrows()
    ]

    with get_connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO indicator_scores
            (date, indicator_id, segment_id, raw_value, percentile, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


def save_segment_scores(df: pd.DataFrame):
    """
    Speichert berechnete Segment-Scores & Ampel-Zustände in segment_scores.
    Erwartete Spalten: ['date', 'segment_id', 's_demand', 's_capacity', 's_price', 's_total', 'signal']
    """
    if df.empty:
        return

    rows = [
        (
            str(r["date"]),
            str(r["segment_id"]),
            float(r["s_demand"]) if pd.notna(r["s_demand"]) else None,
            float(r["s_capacity"]) if pd.notna(r["s_capacity"]) else None,
            float(r["s_price"]) if pd.notna(r["s_price"]) else None,
            float(r["s_total"]) if pd.notna(r["s_total"]) else None,
            str(r["signal"]),
        )
        for _, r in df.iterrows()
    ]

    with get_connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO segment_scores
            (date, segment_id, s_demand, s_capacity, s_price, s_total, signal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


def log_run(status: str, message: str):
    """Schreibt einen Eintrag ins Run-Log."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO run_logs (run_at, status, message) VALUES (?, ?, ?)",
            (now_str, status, message),
        )
        conn.commit()


# ==============================================================================
# LESE-FUNKTIONEN (FÜR ENGINE, NOTIFIER & DASHBOARD)
# ==============================================================================

def get_raw_series(indicator_id: str) -> pd.DataFrame:
    """Lädt die komplette Rohdaten-Historie eines Indikators als DataFrame."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT date, raw_value, status
            FROM raw_indicators
            WHERE indicator_id = ?
            ORDER BY date ASC
            """,
            conn,
            params=(indicator_id,),
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    return df


def get_last_known_value(indicator_id: str):
    """Gibt den letzten gespeicherten Wert (Datum, Wert) für den Fallback zurück."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT date, raw_value
            FROM raw_indicators
            WHERE indicator_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (indicator_id,),
        ).fetchone()
    return row  # (date_str, raw_value) oder None


def get_latest_two_segment_signals() -> dict:
    """
    Gibt pro Segment das aktuellste und das vorletzte Signal zurück.
    Wird vom Notifier genutzt, um echte Statuswechsel auf 'GRUEN' zu erkennen.
    Rückgabe: {segment_id: {"current": {...}, "previous": {...}}}
    """
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT date, segment_id, s_demand, s_capacity, s_price, s_total, signal
            FROM segment_scores
            ORDER BY segment_id, date DESC
            """,
            conn,
        )

    result = {}
    if df.empty:
        return result

    for seg_id, group in df.groupby("segment_id"):
        records = group.head(2).to_dict(orient="records")
        result[seg_id] = {
            "current": records[0] if len(records) >= 1 else None,
            "previous": records[1] if len(records) >= 2 else None,
        }
    return result


def get_segment_history(segment_id: str) -> pd.DataFrame:
    """Lädt die komplette Score-Historie eines Segments für die Plotly-Charts."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT date, s_demand, s_capacity, s_price, s_total, signal
            FROM segment_scores
            WHERE segment_id = ?
            ORDER BY date ASC
            """,
            conn,
            params=(segment_id,),
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_latest_indicator_details(segment_id: str) -> pd.DataFrame:
    """Lädt den aktuellsten Stand der 6 Einzelindikatoren eines Segments."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT i.indicator_id, i.date, i.raw_value, i.percentile, i.status
            FROM indicator_scores i
            INNER JOIN (
                SELECT indicator_id, MAX(date) AS max_date
                FROM indicator_scores
                WHERE segment_id = ?
                GROUP BY indicator_id
            ) latest
            ON i.indicator_id = latest.indicator_id AND i.date = latest.max_date
            WHERE i.segment_id = ?
            """,
            conn,
            params=(segment_id, segment_id),
        )
    return df


def get_last_run_info():
    """Gibt Datum und Status des letzten Updates zurück."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT run_at, status, message FROM run_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row