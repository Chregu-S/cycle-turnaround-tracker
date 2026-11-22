"""
fetcher.py
Lädt alle 60 Indikatoren von FRED, yfinance und Web-Scrapern.
- Resampled alle Daten auf ein einheitliches wöchentliches Raster (Sonntag, 'W-SUN')
- Nutzt Forward-Fill (ffill) für monatliche/quartalsweise Reihen
- Berechnet bei Bedarf YoY-Veränderungen (52 Wochen) zur Saisonbereinigung
- Fehlertolerant: Bei Ausfall wird der letzte bekannte Wert aus SQLite fortgeschrieben
"""

import os
import re
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf
from fredapi import Fred

from config import SEGMENTS, BACKFILL_YEARS
import database as db


def _get_weekly_grid(years: int = BACKFILL_YEARS) -> pd.DatetimeIndex:
    """Erzeugt das einheitliche wöchentliche Datumsraster (jeder Sonntag)."""
    end_date = pd.Timestamp.today().normalize()
    # Auf den letzten abgeschlossenen oder heutigen Sonntag ausrichten
    start_date = end_date - pd.DateOffset(years=years)
    return pd.date_range(start=start_date, end=end_date, freq="W-SUN")


def _resample_to_weekly(series: pd.Series, grid: pd.DatetimeIndex) -> pd.Series:
    """Bringt eine beliebige Zeitreihe auf das Sonntags-Raster mit Forward-Fill."""
    if series is None or series.empty:
        return pd.Series(dtype=float)

    s = series.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s.sort_index()
    # Auf Sonntag resamplen (letzter bekannter Wert der Woche)
    s_weekly = s.resample("W-SUN").last()
    # Auf das globale Raster reindizieren und Lücken vorwärts auffüllen
    s_weekly = s_weekly.reindex(grid).ffill()
    return s_weekly


def _download_yf_close(ticker: str, start_date: str) -> pd.Series:
    """Lädt Schlusskurse eines einzelnen Tickers über yfinance (robust gegen MultiIndex)."""
    df = yf.download(
        ticker,
        start=start_date,
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # Neuere yfinance-Versionen liefern teils MultiIndex-Spalten
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"].iloc[:, 0]
    else:
        close = df["Close"]

    return close.dropna()


def _fetch_fred(fred_client: Fred, symbol: str, start_date: str) -> pd.Series:
    """Lädt eine Zeitreihe von der FRED API."""
    if fred_client is None:
        raise ValueError("FRED_API_KEY fehlt oder ist ungültig.")
    # Extra 1 Jahr Puffer laden, damit YoY (52 Wochen) am Anfang keine Lücken hat
    padded_start = (pd.Timestamp(start_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    s = fred_client.get_series(symbol, observation_start=padded_start)
    if s is None or s.empty:
        raise ValueError(f"FRED lieferte keine Daten für {symbol}")
    return s.dropna()


def _fetch_yf_price(symbol: str, start_date: str) -> pd.Series:
    """Lädt den reinen Kursverlauf eines Tickers."""
    s = _download_yf_close(symbol, start_date)
    if s.empty:
        raise ValueError(f"Keine Kursdaten für {symbol}")
    return s


def _fetch_yf_momentum(symbols: list, window_weeks: int, start_date: str, grid: pd.DatetimeIndex) -> pd.Series:
    """Berechnet das durchschnittliche X-Wochen-Kursmomentum (%) über 1..N Ticker."""
    padded_start = (pd.Timestamp(start_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    series_list = []

    for sym in symbols:
        close = _download_yf_close(sym, padded_start)
        if not close.empty:
            w = close.resample("W-SUN").last().ffill()
            mom = w.pct_change(periods=window_weeks) * 100.0
            series_list.append(mom)

    if not series_list:
        raise ValueError(f"Keine Momentum-Daten für {symbols}")

    combined = pd.concat(series_list, axis=1).mean(axis=1)
    return combined.reindex(grid).ffill()


def _fetch_yf_ratio(symbols: list, start_date: str, grid: pd.DatetimeIndex) -> pd.Series:
    """Berechnet das Verhältnis Ticker A / Ticker B (z. B. SMH/SPY oder Kupfer/Gold)."""
    s1 = _download_yf_close(symbols[0], start_date)
    s2 = _download_yf_close(symbols[1], start_date)
    if s1.empty or s2.empty:
        raise ValueError(f"Ratio-Daten unvollständig für {symbols}")

    w1 = _resample_to_weekly(s1, grid)
    w2 = _resample_to_weekly(s2, grid)
    return (w1 / w2).replace([np.inf, -np.inf], np.nan).ffill()


def _fetch_yf_drawdown(symbols: list, start_date: str, grid: pd.DatetimeIndex) -> pd.Series:
    """
    Berechnet den durchschnittlichen Abstand zum rollierenden 52-Wochen-Hoch (%).
    Dient als robuster Zyklus-/CapEx-Proxy für stark zyklische Branchen.
    """
    padded_start = (pd.Timestamp(start_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    series_list = []

    for sym in symbols:
        close = _download_yf_close(sym, padded_start)
        if not close.empty:
            w = close.resample("W-SUN").last().ffill()
            roll_max = w.rolling(window=52, min_periods=10).max()
            dd = ((w - roll_max) / roll_max) * 100.0
            series_list.append(dd)

    if not series_list:
        raise ValueError(f"Keine Drawdown-Daten für {symbols}")

    combined = pd.concat(series_list, axis=1).mean(axis=1)
    return combined.reindex(grid).ffill()


def _fetch_yf_margin(symbols: list, margin_type: str, start_date: str, grid: pd.DatetimeIndex) -> pd.Series:
    """
    Versucht Quartals-Margen (Gross/Operating/Net) über yfinance zu laden.
    Da yfinance oft nur 4–5 Quartale Historie liefert, nutzen wir für die
    5-Jahres-Vergleichbarkeit ein 26-Wochen-Kursmomentum als stabilen Proxy,
    wenn weniger als 8 Quartale vorliegen.
    """
    row_map = {
        "gross": ["Gross Profit"],
        "operating": ["Operating Income", "EBIT"],
        "net": ["Net Income"],
    }
    target_rows = row_map.get(margin_type, ["Gross Profit"])
    margin_series_list = []

    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            fin = t.quarterly_income_stmt
            if fin is not None and not fin.empty and "Total Revenue" in fin.index:
                rev = fin.loc["Total Revenue"]
                num = None
                for r_name in target_rows:
                    if r_name in fin.index:
                        num = fin.loc[r_name]
                        break
                if num is not None:
                    m = (num / rev).dropna() * 100.0
                    # Nur nutzen, wenn ausreichend lange Historie vorhanden ist
                    if len(m) >= 8:
                        m.index = pd.to_datetime(m.index).tz_localize(None)
                        margin_series_list.append(m.sort_index())
        except Exception:
            continue

    if margin_series_list:
        combined = pd.concat(margin_series_list, axis=1).mean(axis=1)
        return _resample_to_weekly(combined, grid)

    # Stabiler Fallback: 26-Wochen-Kursmomentum der Branchenführer
    return _fetch_yf_momentum(symbols, window_weeks=26, start_date=start_date, grid=grid)


def _fetch_drewry_wci(fallback_ticker: str, start_date: str, grid: pd.DatetimeIndex) -> tuple[pd.Series, str]:
    """
    Scraped den aktuellen Drewry World Container Index (USD pro 40ft-Container).
    Schreibt den aktuellen Wert in die bestehende Historie fort.
    Falls das Scraping fehlschlägt oder noch keine Historie existiert,
    wird sauber auf das ZIM-Kursmomentum zurückgefallen.
    """
    url = "https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    scraped_val = None

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        # Sucht nach typischen Mustern wie "$3,483 per 40ft container"
        match = re.search(r"\$([0-9]{1,2},[0-9]{3}(?:\.[0-9]+)?)\s*(?:per\s*40ft|per\s*FEU)", text, re.IGNORECASE)
        if match:
            scraped_val = float(match.group(1).replace(",", ""))
    except Exception:
        scraped_val = None

    # Prüfen, ob wir bereits genug eigene Drewry-Historie in SQLite haben
    existing = db.get_raw_series("cont_prc_1")
    if scraped_val is not None and not existing.empty and len(existing) >= 52:
        s = existing["raw_value"].copy()
        s.loc[grid[-1]] = scraped_val
        return _resample_to_weekly(s, grid), "OK"

    # Beim Initial-Backfill (oder Scrape-Fehler) nutzen wir den ZIM-Proxy,
    # damit sofort 5 Jahre Historie für das Perzentil vorhanden sind.
    fallback_series = _fetch_yf_momentum([fallback_ticker], window_weeks=13, start_date=start_date, grid=grid)
    status = "FALLBACK_ZIM" if scraped_val is None else "PROXY_ZIM"
    return fallback_series, status


def fetch_all_indicators() -> list[str]:
    """
    Hauptfunktion: Aktualisiert alle 60 Indikatoren und speichert sie in SQLite.
    Gibt eine Liste mit Warnmeldungen zurück (leer, wenn alles sauber lief).
    """
    fred_api_key = os.getenv("FRED_API_KEY")
    fred_client = Fred(api_key=fred_api_key) if fred_api_key else None

    grid = _get_weekly_grid(BACKFILL_YEARS)
    start_date_str = grid[0].strftime("%Y-%m-%d")
    warnings = []

    print(f"Starte Datenabruf ({start_date_str} bis {grid[-1].strftime('%Y-%m-%d')})...")

    for seg_id, seg_cfg in SEGMENTS.items():
        print(f"  -> Segment: {seg_cfg['short_name']}")
        for ind in seg_cfg["indicators"]:
            ind_id = ind["id"]
            source = ind["source"]
            symbol = ind["symbol"]
            params = ind.get("params", {})
            status = "OK"

            try:
                if source == "fred":
                    raw = _fetch_fred(fred_client, symbol, start_date_str)
                    weekly = _resample_to_weekly(raw, grid)
                elif source == "yf_price":
                    raw = _fetch_yf_price(symbol, start_date_str)
                    weekly = _resample_to_weekly(raw, grid)
                elif source == "yf_momentum":
                    weekly = _fetch_yf_momentum(symbol, params.get("window_weeks", 13), start_date_str, grid)
                elif source == "yf_ratio":
                    weekly = _fetch_yf_ratio(symbol, start_date_str, grid)
                elif source == "yf_drawdown":
                    weekly = _fetch_yf_drawdown(symbol, start_date_str, grid)
                elif source == "yf_margin":
                    weekly = _fetch_yf_margin(symbol, params.get("margin_type", "gross"), start_date_str, grid)
                elif source == "scrape_drewry":
                    weekly, status = _fetch_drewry_wci(params.get("fallback_ticker", "ZIM"), start_date_str, grid)
                else:
                    raise ValueError(f"Unbekannte Quelle: {source}")

                # Saisonbereinigung über 52-Wochen-YoY-Veränderung, falls konfiguriert
                if ind.get("yoy", False):
                    weekly = weekly.pct_change(periods=52) * 100.0
                    weekly = weekly.replace([np.inf, -np.inf], np.nan).ffill()

                if weekly.dropna().empty:
                    raise ValueError("Ergebnisreihe ist leer.")

                db.save_raw_series(ind_id, weekly, status=status)

            except Exception as e:
                # Fehlertoleranz: Letzten bekannten Wert aus SQLite beibehalten
                last_known = db.get_last_known_value(ind_id)
                warn_msg = f"[{seg_cfg['short_name']}] {ind['name']} ({ind_id}): {e}"
                warnings.append(warn_msg)
                print(f"     [WARNUNG] {warn_msg}")

                if last_known is not None:
                    fallback_series = pd.Series([last_known[1]], index=[grid[-1]])
                    db.save_raw_series(ind_id, fallback_series, status="FALLBACK_DB")

    return warnings
