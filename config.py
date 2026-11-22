"""
config.py (Version 3.0 – Fokussiertes Boom-and-Bust Alpha-Dashboard)
9 stark zyklische Sub-Segmente (54 Indikatoren):
- Behalten (bewiesene Gewinner): Dry Bulk, Tanker, Maschinenbau, Auto OEMs
- Neu (echte Boom-and-Bust-Zyklen): Chemie, Agrar/Dünger, Reisen/Airlines, Einzelhandel, LNG/LPG
"""

# ==============================================================================
# 1. GLOBALE EINSTELLUNGEN
# ==============================================================================
DB_PATH = "cycle_data.db"
PORTFOLIO_PATH = "portfolio.json"

BACKFILL_YEARS = 15
ROLLING_WINDOW_WEEKS = 260  # 5 Jahre à 52 Wochen

CATEGORY_WEIGHTS = {
    "demand": 0.50,
    "capacity": 0.30,
    "price": 0.20,
}

# ==============================================================================
# 2. AMPEL- & REGIME-SCHWELLENWERTE (STATE MACHINE)
# ==============================================================================
THRESHOLDS = {
    "bottom_level": 25.0,
    "bottom_lookback_wks": 26,
    "green_min": 20.0,
    "green_max": 55.0,
    "demand_ma_wks": 4,

    # Exit- & Frühwarn-Regeln
    "orange_min": 70.0,
    "sell_peak_level": 65.0,
    "sell_lookback_wks": 26,
    "hard_stop_score": 25.0,

    # Regime-Logik (Gewinner aus 15J-Backtest)
    "regime_fast_ema": 6,
    "regime_slow_ema": 20,

    # Technische Filter
    "double_lock_ema_wks": 10,
    "default_trailing_stop": 0.15,
}

# ==============================================================================
# 3. DIE 9 BOOM-AND-BUST SUB-SEGMENTE (54 INDIKATOREN)
# ==============================================================================
SEGMENTS = {
    # --------------------------------------------------------------------------
    # 1. SHIPPING – DRY BULK (BEHALTEN)
    # --------------------------------------------------------------------------
    "shipping_drybulk": {
        "name": "Shipping – Dry Bulk (Eisenerz, Kohle, Getreide)",
        "short_name": "Dry Bulk Shipping",
        "benchmark_etf": "BDRY",
        "stocks": ["SBLK", "GOGL", "GNK", "NMM"],
        "indicators": [
            {"id": "bulk_dem_1", "name": "China/Eisenerz 6M-Momentum (FXI, BHP)", "category": "demand", "source": "yf_momentum", "symbol": ["FXI", "BHP"], "invert": False, "yoy": False, "params": {"window_weeks": 26}},
            {"id": "bulk_dem_2", "name": "US Goods Exports (FRED)", "category": "demand", "source": "fred", "symbol": "BOPTEXP", "invert": False, "yoy": True, "params": {}},
            {"id": "bulk_cap_1", "name": "US Rail Freight Car
