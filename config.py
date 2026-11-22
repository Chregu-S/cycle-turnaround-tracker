"""
config.py (Version 4.0 – 0-Lag Real-Time Boom-and-Bust Core)
7 stark zyklische Sub-Segmente (42 Indikatoren), komplett OHNE langsame FRED-Monatsdaten.
Alle Indikatoren sind tägliche Marktdaten (0W Lag) oder wöchentliche Daten (max. 1W Lag).
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

    # Regime-Logik
    "regime_fast_ema": 6,
    "regime_slow_ema": 20,

    # Technische Filter
    "double_lock_ema_wks": 10,
    "default_trailing_stop": 0.15,
}

# ==============================================================================
# 3. DIE 7 BOOM-AND-BUST SUB-SEGMENTE (42 ECHTZEIT-INDIKATOREN)
# ==============================================================================
SEGMENTS = {
    # --------------------------------------------------------------------------
    # 1. SHIPPING – DRY BULK (0-LAG)
    # --------------------------------------------------------------------------
    "shipping_drybulk": {
        "name": "Shipping – Dry Bulk (Eisenerz, Kohle, Getreide)",
        "short_name": "Dry Bulk Shipping",
        "benchmark_etf": "BDRY",
        "stocks": ["SBLK", "GOGL", "GNK", "NMM", "DSX", "SB", "SHIP", "PANL", "HSHP", "CMBT"],
        "indicators": [
            {"id": "bulk_dem_1", "name": "China/Eisenerz 6M-Momentum (FXI, BHP)", "category": "demand", "source": "yf_momentum", "symbol": ["FXI", "BHP"], "invert": False, "yoy": False, "params": {"window_weeks": 26}},
            {"id": "bulk_dem_2", "name": "Kupfer/Gold-Ratio (HG=F / GC=F)", "category": "demand", "source": "yf_ratio", "symbol": ["HG=F", "GC=F"], "invert": False, "yoy": False, "params": {}},
            {"id": "bulk_cap_1", "name": "US High-Yield Credit Spreads (FRED Daily)", "category": "capacity", "source": "fred", "symbol": "BAMLH0A0HYM2", "invert": True, "yoy": False, "params": {}},
            {"id": "bulk_cap_2", "name": "SBLK & GOGL Valuation/CapEx-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["SBLK", "GOGL"], "invert": False, "yoy": False, "params": {}},
            {"id": "bulk_prc_1", "name": "Baltic Dry Proxy (BDRY ETF)", "category": "price", "source": "yf_price", "symbol": "BDRY", "invert": False, "yoy": False, "params": {}},
            {"id": "bulk_prc_2", "name": "Operating Margin / Trend (SBLK, GNK)", "category": "price", "source": "yf_margin", "symbol": ["SBLK", "GNK"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 2. SHIPPING – TANKER (0-LAG)
    # --------------------------------------------------------------------------
    "shipping_tanker": {
        "name": "Shipping – Tanker (Crude & Product)",
        "short_name": "Tanker Shipping",
        "benchmark_etf": "FRO",
        "stocks": ["FRO", "STNG", "INSW", "DHT", "TNK", "TRMD", "ECO", "ASC", "NAT", "OET"],
        "indicators": [
            {"id": "tank_dem_1", "name": "Oil Refiners ETF Momentum (CRAK)", "category": "demand", "source": "yf_momentum", "symbol": ["CRAK"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "tank_dem_2", "name": "Brent Crude Oil Price YoY (FRED Daily)", "category": "demand", "source": "fred", "symbol": "DCOILBRENTEU", "invert": False, "yoy": True, "params": {}},
            {"id": "tank_cap_1", "name": "Crack Spread Proxy (RB=F / CL=F)", "category": "capacity", "source": "yf_ratio", "symbol": ["RB=F", "CL=F"], "invert": False, "yoy": False, "params": {}},
            {"id": "tank_cap_2", "name": "FRO & STNG Flotten-/CapEx-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["FRO", "STNG"], "invert": False, "yoy": False, "params": {}},
            {"id": "tank_prc_1", "name": "Tanker Freight Proxy (BWET ETF)", "category": "price", "source": "yf_price", "symbol": "BWET", "invert": False, "yoy": False, "params": {}},
            {"id": "tank_prc_2", "name": "Net Margin / Trend (FRO, STNG)", "category": "price", "source": "yf_margin", "symbol": ["FRO", "STNG"], "invert": False, "yoy": False, "params": {"margin_type": "net"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 3. INDUSTRIE – ALLGEMEINER MASCHINENBAU (0-LAG)
    # --------------------------------------------------------------------------
    "ind_machinery": {
        "name": "Industrie – Allgemeiner Maschinenbau",
        "short_name": "Maschinenbau",
        "benchmark_etf": "XLI",
        "stocks": ["CAT", "PH", "ETN", "ROK", "CMI", "URI", "PCAR", "DOV", "ITW", "EMR"],
        "indicators": [
            {"id": "mac_dem_1", "name": "Kupfer/Gold-Ratio (HG=F / GC=F)", "category": "demand", "source": "yf_ratio", "symbol": ["HG=F", "GC=F"], "invert": False, "yoy": False, "params": {}},
            {"id": "mac_dem_2", "name": "Industrie vs. Versorger Ratio (XLI/XLU)", "category": "demand", "source": "yf_ratio", "symbol": ["XLI", "XLU"], "invert": False, "yoy": False, "params": {}},
            {"id": "mac_cap_1", "name": "US High-Yield Credit Spreads (FRED Daily)", "category": "capacity", "source": "fred", "symbol": "BAMLH0A0HYM2", "invert": True, "yoy": False, "params": {}},
            {"id": "mac_cap_2", "name": "US Erstanträge Arbeitslosenhilfe YoY (FRED Weekly)", "category": "capacity", "source": "fred", "symbol": "ICSA", "invert": True, "yoy": True, "params": {}},
            {"id": "mac_prc_1", "name": "Maschinenbau 13W-Momentum (PH, ETN, ROK, CAT)", "category": "price", "source": "yf_momentum", "symbol": ["PH", "ETN", "ROK", "CAT"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "mac_prc_2", "name": "Operating Margin Trend (PH, ETN, ROK)", "category": "price", "source": "yf_margin", "symbol": ["PH", "ETN", "ROK"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 4. AUTOMOBILE – OEMS (0-LAG)
    # --------------------------------------------------------------------------
    "auto_oem": {
        "name": "Automobile – OEMs (Massenmarkt & Volumen)",
        "short_name": "Auto OEMs",
        "benchmark_etf": "CARZ",
        "stocks": ["GM", "F", "STLA", "TM", "HMC", "RACE", "TSLA", "RIVN", "LI", "BYDDY"],
        "indicators": [
            {"id": "aut_dem_1", "name": "Zykl. vs. Defensiver Konsum (XLY/XLP)", "category": "demand", "source": "yf_ratio", "symbol": ["XLY", "XLP"], "invert": False, "yoy": False, "params": {}},
            {"id": "aut_dem_2", "name": "US Erstanträge Arbeitslosenhilfe YoY (FRED Weekly)", "category": "demand", "source": "fred", "symbol": "ICSA", "invert": True, "yoy": True, "params": {}},
            {"id": "aut_cap_1", "name": "US High-Yield Credit Spreads (FRED Daily)", "category": "capacity", "source": "fred", "symbol": "BAMLH0A0HYM2", "invert": True, "yoy": False, "params": {}},
            {"id": "aut_cap_2", "name": "Relativstärke Auto vs. Markt (CARZ/SPY)", "category": "capacity", "source": "yf_ratio", "symbol": ["CARZ", "SPY"], "invert": False, "yoy": False, "params": {}},
            {"id": "aut_prc_1", "name": "Auto OEMs 13W-Momentum (GM, F, STLA, TM)", "category": "price", "source": "yf_momentum", "symbol": ["GM", "F", "STLA", "TM"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "aut_prc_2", "name": "Operating Margin Trend (GM, F, STLA)", "category": "price", "source": "yf_margin", "symbol": ["GM", "F", "STLA"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 5. GRUNDSTOFFE – AGRAR & DÜNGEMITTEL (0-LAG)
    # --------------------------------------------------------------------------
    "agri_fert": {
        "name": "Grundstoffe – Agrar & Düngemittel",
        "short_name": "Agrar & Dünger",
        "benchmark_etf": "MOO",
        "stocks": ["NTR", "MOS", "CF", "DE", "AGCO", "CNH", "FMC", "CTVA", "BG", "ADM"],
        "indicators": [
            {"id": "agr_dem_1", "name": "Corn Futures Preis (ZC=F)", "category": "demand", "source": "yf_price", "symbol": "ZC=F", "invert": False, "yoy": False, "params": {}},
            {"id": "agr_dem_2", "name": "Soybean Futures Preis (ZS=F)", "category": "demand", "source": "yf_price", "symbol": "ZS=F", "invert": False, "yoy": False, "params": {}},
            {"id": "agr_cap_1", "name": "Natural Gas Cost Proxy (NG=F)", "category": "capacity", "source": "yf_price", "symbol": "NG=F", "invert": True, "yoy": False, "params": {}},
            {"id": "agr_cap_2", "name": "NTR & MOS 52W-Drawdown/Zyklus-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["NTR", "MOS", "CF"], "invert": False, "yoy": False, "params": {}},
            {"id": "agr_prc_1", "name": "Relativstärke Agrar vs. Markt (MOO/SPY)", "category": "price", "source": "yf_ratio", "symbol": ["MOO", "SPY"], "invert": False, "yoy": False, "params": {}},
            {"id": "agr_prc_2", "name": "Gross Margin / Trend (NTR, MOS, CF)", "category": "price", "source": "yf_margin", "symbol": ["NTR", "MOS", "CF"], "invert": False, "yoy": False, "params": {"margin_type": "gross"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 6. ZYKL. KONSUM – EINZELHANDEL & BEKLEIDUNG (0-LAG)
    # --------------------------------------------------------------------------
    "cons_retail": {
        "name": "Zykl. Konsum – Einzelhandel, Bekleidung & Luxus",
        "short_name": "Einzelhandel",
        "benchmark_etf": "XRT",
        "stocks": ["TGT", "ANF", "NKE", "RL", "URBN", "AEO", "LULU", "DECK", "GAP", "BBY"],
        "indicators": [
            {"id": "ret_dem_1", "name": "Zykl. vs. Defensiver Konsum (XLY/XLP)", "category": "demand", "source": "yf_ratio", "symbol": ["XLY", "XLP"], "invert": False, "yoy": False, "params": {}},
            {"id": "ret_dem_2", "name": "US Erstanträge Arbeitslosenhilfe YoY (FRED Weekly)", "category": "demand", "source": "fred", "symbol": "ICSA", "invert": True, "yoy": True, "params": {}},
            {"id": "ret_cap_1", "name": "US High-Yield Credit Spreads (FRED Daily)", "category": "capacity", "source": "fred", "symbol": "BAMLH0A0HYM2", "invert": True, "yoy": False, "params": {}},
            {"id": "ret_cap_2", "name": "Relativstärke Retail vs. Markt (XRT/SPY)", "category": "capacity", "source": "yf_ratio", "symbol": ["XRT", "SPY"], "invert": False, "yoy": False, "params": {}},
            {"id": "ret_prc_1", "name": "Retail 13W-Momentum (TGT, ANF, NKE, RL)", "category": "price", "source": "yf_momentum", "symbol": ["TGT", "ANF", "NKE", "RL"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "ret_prc_2", "name": "Gross Margin / Trend (TGT, NKE, RL)", "category": "price", "source": "yf_margin", "symbol": ["TGT", "NKE", "RL"], "invert": False, "yoy": False, "params": {"margin_type": "gross"}},
        ],
    },

    # --------------------------------------------------------------------------
    # 7. SHIPPING – LNG / LPG GAS CARRIER (0-LAG)
    # --------------------------------------------------------------------------
    "shipping_lng": {
        "name": "Shipping – LNG / LPG Gas Carrier",
        "short_name": "LNG / LPG Shipping",
        "benchmark_etf": "FLNG",
        "stocks": ["FLNG", "LPG", "GLNG", "BWLP", "NVGS", "CLCO", "DLNG", "LNG", "NFE", "VG"],
        "indicators": [
            {"id": "lng_dem_1", "name": "US Natural Gas Futures (NG=F)", "category": "demand", "source": "yf_price", "symbol": "NG=F", "invert": False, "yoy": False, "params": {}},
            {"id": "lng_dem_2", "name": "Brent Crude Oil Price YoY (FRED Daily)", "category": "demand", "source": "fred", "symbol": "DCOILBRENTEU", "invert": False, "yoy": True, "params": {}},
            {"id": "lng_cap_1", "name": "FLNG & LPG 52W-Drawdown/Flotten-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["FLNG", "LPG"], "invert": False, "yoy": False, "params": {}},
            {"id": "lng_cap_2", "name": "Relativstärke LNG vs. Markt (FLNG/SPY)", "category": "capacity", "source": "yf_ratio", "symbol": ["FLNG", "SPY"], "invert": False, "yoy": False, "params": {}},
            {"id": "lng_prc_1", "name": "LNG/LPG 13-Wochen-Kursmomentum", "category": "price", "source": "yf_momentum", "symbol": ["FLNG", "LPG", "GLNG"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "lng_prc_2", "name": "Operating Margin / Trend (FLNG, LPG, GLNG)", "category": "price", "source": "yf_margin", "symbol": ["FLNG", "LPG", "GLNG"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },
}
