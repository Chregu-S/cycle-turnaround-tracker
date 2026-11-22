"""
config.py (Version 3.1 – 7-Sector Boom-and-Bust Core)
Validated sectors: Dry Bulk, Tanker, Maschinenbau, Auto OEMs, Agrar/Dünger, Einzelhandel, LNG/LPG
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
# 3. DIE 7 BOOM-AND-BUST SUB-SEGMENTE (42 INDIKATOREN)
# ==============================================================================
SEGMENTS = {
    "shipping_drybulk": {
        "name": "Shipping – Dry Bulk (Eisenerz, Kohle, Getreide)",
        "short_name": "Dry Bulk Shipping",
        "benchmark_etf": "BDRY",
        "stocks": ["SBLK", "GOGL", "GNK", "NMM"],
        "indicators": [
            {"id": "bulk_dem_1", "name": "China/Eisenerz 6M-Momentum (FXI, BHP)", "category": "demand", "source": "yf_momentum", "symbol": ["FXI", "BHP"], "invert": False, "yoy": False, "params": {"window_weeks": 26}},
            {"id": "bulk_dem_2", "name": "US Goods Exports (FRED)", "category": "demand", "source": "fred", "symbol": "BOPTEXP", "invert": False, "yoy": True, "params": {}},
            {"id": "bulk_cap_1", "name": "US Rail Freight Carloads (FRED)", "category": "capacity", "source": "fred", "symbol": "RAILFRTCARLOADSD11", "invert": False, "yoy": True, "params": {}},
            {"id": "bulk_cap_2", "name": "SBLK & GOGL Valuation/CapEx-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["SBLK", "GOGL"], "invert": False, "yoy": False, "params": {}},
            {"id": "bulk_prc_1", "name": "Baltic Dry Proxy (BDRY ETF)", "category": "price", "source": "yf_price", "symbol": "BDRY", "invert": False, "yoy": False, "params": {}},
            {"id": "bulk_prc_2", "name": "Operating Margin / Trend (SBLK, GNK)", "category": "price", "source": "yf_margin", "symbol": ["SBLK", "GNK"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },
    "shipping_tanker": {
        "name": "Shipping – Tanker (Crude & Product)",
        "short_name": "Tanker Shipping",
        "benchmark_etf": "FRO",
        "stocks": ["FRO", "STNG", "INSW", "DHT"],
        "indicators": [
            {"id": "tank_dem_1", "name": "Oil Refiners ETF Momentum (CRAK)", "category": "demand", "source": "yf_momentum", "symbol": ["CRAK"], "invert": False, "yoy": False, "params": {"window_weeks": 13}},
            {"id": "tank_dem_2", "name": "Brent Crude Oil Price YoY (FRED)", "category": "demand", "source": "fred", "symbol": "DCOILBRENTEU", "invert": False, "yoy": True, "params": {}},
            {"id": "tank_cap_1", "name": "Crack Spread Proxy (RB=F / CL=F)", "category": "capacity", "source": "yf_ratio", "symbol": ["RB=F", "CL=F"], "invert": False, "yoy": False, "params": {}},
            {"id": "tank_cap_2", "name": "FRO & STNG Flotten-/CapEx-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["FRO", "STNG"], "invert": False, "yoy": False, "params": {}},
            {"id": "tank_prc_1", "name": "Tanker Freight Proxy (BWET ETF)", "category": "price", "source": "yf_price", "symbol": "BWET", "invert": False, "yoy": False, "params": {}},
            {"id": "tank_prc_2", "name": "Net Margin / Trend (FRO, STNG)", "category": "price", "source": "yf_margin", "symbol": ["FRO", "STNG"], "invert": False, "yoy": False, "params": {"margin_type": "net"}},
        ],
    },
    "ind_machinery": {
        "name": "Industrie – Allgemeiner Maschinenbau",
        "short_name": "Maschinenbau",
        "benchmark_etf": "XLI",
        "stocks": ["PH", "ETN", "ROK", "CAT"],
        "indicators": [
            {"id": "mac_dem_1", "name": "Machinery New Orders (FRED)", "category": "demand", "source": "fred", "symbol": "A33SNO", "invert": False, "yoy": True, "params": {}},
            {"id": "mac_dem_2", "name": "Core Capital Goods Orders (FRED)", "category": "demand", "source": "fred", "symbol": "ANDENO", "invert": False, "yoy": True, "params": {}},
            {"id": "mac_cap_1", "name": "Machinery Inventories/Sales (FRED)", "category": "capacity", "source": "fred", "symbol": "A33SIS", "invert": True, "yoy": False, "params": {}},
            {"id": "mac_cap_2", "name": "Capacity Utilization Machinery (FRED)", "category": "capacity", "source": "fred", "symbol": "CAPUTLG333S", "invert": False, "yoy": False, "params": {}},
            {"id": "mac_prc_1", "name": "PPI Machinery (FRED)", "category": "price", "source": "fred", "symbol": "PCU333333", "invert": False, "yoy": True, "params": {}},
            {"id": "mac_prc_2", "name": "Operating Margin Trend (PH, ETN, ROK)", "category": "price", "source": "yf_margin", "symbol": ["PH", "ETN", "ROK"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },
    "auto_oem": {
        "name": "Automobile – OEMs (Massenmarkt & Volumen)",
        "short_name": "Auto OEMs",
        "benchmark_etf": "CARZ",
        "stocks": ["GM", "F", "STLA", "TM"],
        "indicators": [
            {"id": "aut_dem_1", "name": "US Light Vehicle Sales (FRED)", "category": "demand", "source": "fred", "symbol": "ALTSALES", "invert": False, "yoy": False, "params": {}},
            {"id": "aut_dem_2", "name": "US Consumer Sentiment (FRED)", "category": "demand", "source": "fred", "symbol": "UMCSENT", "invert": False, "yoy": False, "params": {}},
            {"id": "aut_cap_1", "name": "Auto Inventories/Sales Ratio (FRED)", "category": "capacity", "source": "fred", "symbol": "AISRSA", "invert": True, "yoy": False, "params": {}},
            {"id": "aut_cap_2", "name": "Motor Vehicles Production (FRED)", "category": "capacity", "source": "fred", "symbol": "IPG3361T3S", "invert": False, "yoy": True, "params": {}},
            {"id": "aut_prc_1", "name": "CPI New Vehicles YoY (FRED)", "category": "price", "source": "fred", "symbol": "CUSR0000SETA01", "invert": False, "yoy": True, "params": {}},
            {"id": "aut_prc_2", "name": "Operating Margin Trend (GM, F, STLA)", "category": "price", "source": "yf_margin", "symbol": ["GM", "F", "STLA"], "invert": False, "yoy": False, "params": {"margin_type": "operating"}},
        ],
    },
    "agri_fert": {
        "name": "Grundstoffe – Agrar & Düngemittel",
        "short_name": "Agrar & Dünger",
        "benchmark_etf": "MOO",
        "stocks": ["NTR", "MOS", "CF", "DE"],
        "indicators": [
            {"id": "agr_dem_1", "name": "Corn Futures Preis (ZC=F)", "category": "demand", "source": "yf_price", "symbol": "ZC=F", "invert": False, "yoy": False, "params": {}},
            {"id": "agr_dem_2", "name": "Soybean Futures Preis (ZS=F)", "category": "demand", "source": "yf_price", "symbol": "ZS=F", "invert": False, "yoy": False, "params": {}},
            {"id": "agr_cap_1", "name": "Natural Gas Cost Proxy (NG=F)", "category": "capacity", "source": "yf_price", "symbol": "NG=F", "invert": True, "yoy": False, "params": {}},
            {"id": "agr_cap_2", "name": "NTR & MOS 52W-Drawdown/Zyklus-Proxy", "category": "capacity", "source": "yf_drawdown", "symbol": ["NTR", "MOS", "CF"], "invert": False, "yoy": False, "params": {}},
            {"id": "agr_prc_1", "name": "PPI Agricultural Chemicals YoY (FRED)", "category": "price", "source": "fred", "symbol": "WPU065", "invert": False, "yoy": True, "params": {}},
            {"id": "agr_prc_2", "name": "Gross Margin / Trend (NTR, MOS, CF)", "category": "price", "source": "yf_margin", "symbol": ["NTR", "MOS", "CF"], "invert": False, "yoy": False, "params": {"margin_type": "gross"}},
        ],
    },
    "cons_retail": {
        "name": "Zykl. Konsum – Einzelhandel, Bekleidung & Luxus",
        "short_name": "Einzelhandel",
        "benchmark_etf": "XRT",
        "stocks": ["TGT", "ANF", "NKE", "RL"],
        "indicators": [
            {"id": "ret_dem_1", "name": "US Advance Retail Sales YoY (FRED)", "category": "demand", "source": "fred", "symbol": "RSXFS", "invert": False, "yoy": True, "params": {}},
            {"id": "ret_dem_2", "name": "US Clothing Store Sales YoY (FRED)", "category": "demand", "source": "fred", "symbol": "MRTSSM448USN", "invert": False, "yoy": True, "params": {}},
            {"id": "ret_cap_1", "name": "US Retail Inventories/Sales Ratio (FRED)", "category": "capacity", "source": "fred", "symbol": "RETAILIRSA", "invert": True, "yoy": False, "params": {}},
            {"id": "ret_cap_2", "name": "Relativstärke Retail vs. Markt (XRT/SPY)", "category": "capacity", "source": "yf_ratio", "symbol": ["XRT", "SPY"], "invert": False, "yoy": False, "params": {}},
            {"id": "ret_prc_1", "name": "CPI Apparel YoY (FRED)", "category": "price", "source": "fred", "symbol": "CPIAPPSL", "invert": False, "yoy": True, "params": {}},
            {"id": "ret_prc_2", "name": "Gross Margin / Trend (TGT, NKE, RL)", "category": "price", "source": "yf_margin", "symbol": ["TGT", "NKE", "RL"], "invert": False, "yoy": False, "params": {"margin_type": "gross"}},
        ],
    },
    "shipping_lng": {
        "name": "Shipping – LNG / LPG Gas Carrier",
        "short_name": "LNG / LPG Shipping",
        "benchmark_etf": "FLNG",
        "stocks": ["FLNG", "LPG", "GLNG", "BWLP"],
        "indicators": [
            {"id": "lng_dem_1", "name": "US Natural Gas Futures (NG=F)", "category": "demand", "source": "yf_price", "symbol": "NG=F", "invert": False, "yoy
