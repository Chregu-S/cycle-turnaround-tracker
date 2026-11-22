"""
config.py
Zentrale Konfiguration für den Cycle Turnaround Tracker.
Enthält alle 10 zyklischen Sub-Segmente, 60 Indikatoren, Gewichtungen und Ampel-Regeln.
"""

# ==============================================================================
# 1. GLOBALE EINSTELLUNGEN
# ==============================================================================
DB_PATH = "cycle_data.db"

# Beim ersten Lauf werden 6 Jahre geladen, damit sofort ein 5-Jahres-Perzentil
# (260 Wochen) für das komplette letzte Jahr berechnet werden kann.
BACKFILL_YEARS = 6
ROLLING_WINDOW_WEEKS = 260  # 5 Jahre à 52 Wochen

# Kategorie-Gewichtungen (Summe = 1.0)
CATEGORY_WEIGHTS = {
    "demand": 0.50,    # Nachfrage-Frühindikatoren
    "capacity": 0.30,  # Kapazität & Lagerbestände
    "price": 0.20,     # Preise & Margen
}

# Ampel-Schwellenwerte (State Machine)
THRESHOLDS = {
    "bottom_level": 25.0,       # Tiefpunkt-Schwelle (Bodenbildung)
    "bottom_lookback_wks": 26,  # Muss in den letzten 26 Wochen < 25 gewesen sein
    "green_min": 20.0,          # Untergrenze für GRÜN
    "green_max": 55.0,          # Obergrenze für GRÜN (darüber = BLAU / Mid-Cycle)
    "demand_ma_wks": 4,         # Nachfrage-Score muss über eigenem 4-Wochen-Schnitt liegen
}

# ==============================================================================
# 2. DIE 10 SUB-SEGMENTE & 60 INDIKATOREN
# ==============================================================================
# Aufbau jedes Indikators:
# - id:       Eindeutiger Schlüssel für die Datenbank
# - name:     Anzeigename im Dashboard
# - category: "demand" (50%), "capacity" (30%) oder "price" (20%)
# - source:   Datenquelle:
#             * "fred"          -> FRED API Zeitreihe
#             * "yf_price"      -> Aktueller Kurs (z. B. ETF oder Future)
#             * "yf_momentum"   -> Prozentuale Kursänderung über X Wochen
#             * "yf_ratio"      -> Relativstärke Ticker A / Ticker B
#             * "yf_drawdown"   -> Abstand zum 52-Wochen-Hoch (CapEx/Zyklus-Proxy)
#             * "yf_margin"     -> Quartals-Marge (mit Fallback auf 26W-Kursmomentum)
#             * "scrape_drewry" -> Web-Scraper für Drewry WCI (mit ZIM-Fallback)
# - symbol:   FRED-Code oder Ticker-Symbol(e)
# - invert:   True = Kontrazyklisch (niedriger Wert = bullisch -> 100 - Perzentil)
# - yoy:      True = 52-Wochen-Veränderung (für nicht-saisonbereinigte Reihen)
# - params:   Zusätzliche Parameter je nach Quelle

SEGMENTS = {
    # --------------------------------------------------------------------------
    # 1. SHIPPING – CONTAINER
    # --------------------------------------------------------------------------
    "shipping_container": {
        "name": "Shipping – Container (Liner & Charter)",
        "short_name": "Container Shipping",
        "indicators": [
            {
                "id": "cont_dem_1",
                "name": "US Retail Inventories/Sales (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "RETAILIRSA",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "cont_dem_2",
                "name": "US Manufacturing New Orders (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "AMTMNO",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "cont_cap_1",
                "name": "Cass Freight Shipments Index (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "FRGSHPUSM649NCIS",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "cont_cap_2",
                "name": "Maersk & ZIM 52W-Drawdown/CapEx-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["MAERSK-B.CO", "ZIM"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "cont_prc_1",
                "name": "Drewry WCI Container Spotrate",
                "category": "price",
                "source": "scrape_drewry",
                "symbol": "DREWRY_WCI",
                "invert": False,
                "yoy": False,
                "params": {"fallback_ticker": "ZIM"},
            },
            {
                "id": "cont_prc_2",
                "name": "Gross Margin / Trend (ZIM, HLAG)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["ZIM", "HLAG.DE"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "gross"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 2. SHIPPING – DRY BULK
    # --------------------------------------------------------------------------
    "shipping_drybulk": {
        "name": "Shipping – Dry Bulk (Eisenerz, Kohle, Getreide)",
        "short_name": "Dry Bulk Shipping",
        "indicators": [
            {
                "id": "bulk_dem_1",
                "name": "China/Eisenerz 6M-Momentum (FXI, BHP)",
                "category": "demand",
                "source": "yf_momentum",
                "symbol": ["FXI", "BHP"],
                "invert": False,
                "yoy": False,
                "params": {"window_weeks": 26},
            },
            {
                "id": "bulk_dem_2",
                "name": "US Goods Exports (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "BOPTEXP",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "bulk_cap_1",
                "name": "US Rail Freight Carloads (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "RAILFRTCARLOADSD11",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "bulk_cap_2",
                "name": "SBLK & GOGL Valuation/CapEx-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["SBLK", "GOGL"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "bulk_prc_1",
                "name": "Baltic Dry Proxy (BDRY ETF)",
                "category": "price",
                "source": "yf_price",
                "symbol": "BDRY",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "bulk_prc_2",
                "name": "Operating Margin / Trend (SBLK, GNK)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["SBLK", "GNK"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "operating"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 3. SHIPPING – TANKER
    # --------------------------------------------------------------------------
    "shipping_tanker": {
        "name": "Shipping – Tanker (Crude & Product)",
        "short_name": "Tanker Shipping",
        "indicators": [
            {
                "id": "tank_dem_1",
                "name": "US Refinery Utilization (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "WPULEUS3",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "tank_dem_2",
                "name": "US Crude Oil Inputs to Refineries (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "WCRRIUS2",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "tank_cap_1",
                "name": "US Commercial Crude Oil Stocks (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "WCESTUS1",
                "invert": True,
                "yoy": True,
                "params": {},
            },
            {
                "id": "tank_cap_2",
                "name": "FRO & STNG Flotten-/CapEx-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["FRO", "STNG"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "tank_prc_1",
                "name": "Tanker Freight Proxy (BWET ETF)",
                "category": "price",
                "source": "yf_price",
                "symbol": "BWET",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "tank_prc_2",
                "name": "Net Margin / Trend (FRO, STNG)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["FRO", "STNG"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "net"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 4. HALBLEITER – MEMORY (DRAM & NAND)
    # --------------------------------------------------------------------------
    "semi_memory": {
        "name": "Halbleiter – Memory (DRAM & NAND)",
        "short_name": "Semis: Memory",
        "indicators": [
            {
                "id": "mem_dem_1",
                "name": "US Computer & Electronic New Orders (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "A34SNO",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "mem_dem_2",
                "name": "Relativstärke Semis vs. Markt (SMH/SPY)",
                "category": "demand",
                "source": "yf_ratio",
                "symbol": ["SMH", "SPY"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "mem_cap_1",
                "name": "MU & WDC Inventory/Valuation-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["MU", "WDC"],
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "mem_cap_2",
                "name": "Semiconductor Production YoY (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "IPG3344S",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "mem_prc_1",
                "name": "Micron (MU) Gross Margin Trend",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["MU"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "gross"},
            },
            {
                "id": "mem_prc_2",
                "name": "MU & WDC 13-Wochen-Preismomentum",
                "category": "price",
                "source": "yf_momentum",
                "symbol": ["MU", "WDC"],
                "invert": False,
                "yoy": False,
                "params": {"window_weeks": 13},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 5. HALBLEITER – LOGIC, ANALOG & AUTOMOTIVE
    # --------------------------------------------------------------------------
    "semi_logic": {
        "name": "Halbleiter – Logic, Analog & Automotive Chips",
        "short_name": "Semis: Logic & Analog",
        "indicators": [
            {
                "id": "log_dem_1",
                "name": "Industrial Production Semiconductors (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "IPG3344S",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "log_dem_2",
                "name": "Nondefense Capital Goods Orders (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "NEWORDER",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "log_cap_1",
                "name": "Capacity Utilization Electronics (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "CAPUTLG334S",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "log_cap_2",
                "name": "TXN & ADI Inventory-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["TXN", "ADI"],
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "log_prc_1",
                "name": "PHLX Semiconductor Index Momentum (^SOX)",
                "category": "price",
                "source": "yf_momentum",
                "symbol": ["^SOX"],
                "invert": False,
                "yoy": False,
                "params": {"window_weeks": 13},
            },
            {
                "id": "log_prc_2",
                "name": "Gross Margin Trend (TXN, ADI, NXPI)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["TXN", "ADI", "NXPI"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "gross"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 6. INDUSTRIE & BAU – WOHNUNGSBAU & BAUZULIEFERER
    # --------------------------------------------------------------------------
    "ind_housing": {
        "name": "Industrie & Bau – Wohnungsbau & Bauzulieferer",
        "short_name": "Wohnungsbau",
        "indicators": [
            {
                "id": "hou_dem_1",
                "name": "US Building Permits (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "PERMIT",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "hou_dem_2",
                "name": "30Y US Mortgage Rate (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "MORTGAGE30US",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "hou_cap_1",
                "name": "Monthly Supply of New Houses (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "MSACSR",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "hou_cap_2",
                "name": "Construction Materials Inv/Sales (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "A32SIS",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "hou_prc_1",
                "name": "PPI Construction Materials (FRED)",
                "category": "price",
                "source": "fred",
                "symbol": "WPUSI012011",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "hou_prc_2",
                "name": "Gross Margin Trend (DHI, LEN)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["DHI", "LEN"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "gross"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 7. INDUSTRIE & BAU – ALLGEMEINER MASCHINENBAU
    # --------------------------------------------------------------------------
    "ind_machinery": {
        "name": "Industrie & Bau – Allgemeiner Maschinenbau",
        "short_name": "Maschinenbau",
        "indicators": [
            {
                "id": "mac_dem_1",
                "name": "Machinery New Orders (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "A33SNO",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "mac_dem_2",
                "name": "Core Capital Goods Orders (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "ANDENO",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "mac_cap_1",
                "name": "Machinery Inventories/Sales (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "A33SIS",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "mac_cap_2",
                "name": "Capacity Utilization Machinery (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "CAPUTLG333S",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "mac_prc_1",
                "name": "PPI Machinery (FRED)",
                "category": "price",
                "source": "fred",
                "symbol": "PCU333333",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "mac_prc_2",
                "name": "Operating Margin Trend (PH, ETN, ROK)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["PH", "ETN", "ROK"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "operating"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 8. AUTOMOBILE – OEMS
    # --------------------------------------------------------------------------
    "auto_oem": {
        "name": "Automobile – OEMs (Massenmarkt & Volumen)",
        "short_name": "Auto OEMs",
        "indicators": [
            {
                "id": "aut_dem_1",
                "name": "US Light Vehicle Sales (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "ALTSALES",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "aut_dem_2",
                "name": "US Consumer Sentiment (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "UMCSENT",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "aut_cap_1",
                "name": "Auto Inventories/Sales Ratio (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "AISRSA",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "aut_cap_2",
                "name": "Motor Vehicles Production (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "IPG3361T3S",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "aut_prc_1",
                "name": "CPI New Vehicles YoY (FRED)",
                "category": "price",
                "source": "fred",
                "symbol": "CUSR0000SETA01",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "aut_prc_2",
                "name": "Operating Margin Trend (GM, F, STLA)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["GM", "F", "STLA"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "operating"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 9. GRUNDSTOFFE – INDUSTRIEMETALLE (KUPFER)
    # --------------------------------------------------------------------------
    "metals_copper": {
        "name": "Grundstoffe – Industriemetalle (v. a. Kupfer)",
        "short_name": "Kupfer & Metalle",
        "indicators": [
            {
                "id": "cop_dem_1",
                "name": "US Total Construction Spending (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "TTLCONS",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "cop_dem_2",
                "name": "Copper/Gold Ratio (HG=F / GC=F)",
                "category": "demand",
                "source": "yf_ratio",
                "symbol": ["HG=F", "GC=F"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "cop_cap_1",
                "name": "Industrial Production Mining (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "IPMINE",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "cop_cap_2",
                "name": "FCX & SCCO CapEx/Valuation-Proxy",
                "category": "capacity",
                "source": "yf_drawdown",
                "symbol": ["FCX", "SCCO"],
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "cop_prc_1",
                "name": "Copper Futures Preis (HG=F)",
                "category": "price",
                "source": "yf_price",
                "symbol": "HG=F",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "cop_prc_2",
                "name": "Gross Margin Trend (FCX, SCCO)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["FCX", "SCCO"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "gross"},
            },
        ],
    },

    # --------------------------------------------------------------------------
    # 10. FINANZEN – GESCHÄFTSBANKEN & KREDITMARKT
    # --------------------------------------------------------------------------
    "fin_banks": {
        "name": "Finanzen – Geschäftsbanken & Kreditmarkt",
        "short_name": "Banken & Kredit",
        "indicators": [
            {
                "id": "bnk_dem_1",
                "name": "Senior Loan Officer Survey: Tightening (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "DRTSCILM",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "bnk_dem_2",
                "name": "Commercial & Industrial Loans (FRED)",
                "category": "demand",
                "source": "fred",
                "symbol": "BUSLOANS",
                "invert": False,
                "yoy": True,
                "params": {},
            },
            {
                "id": "bnk_cap_1",
                "name": "Delinquency Rate C&I Loans (FRED)",
                "category": "capacity",
                "source": "fred",
                "symbol": "DRBLACBS",
                "invert": True,
                "yoy": False,
                "params": {},
            },
            {
                "id": "bnk_cap_2",
                "name": "US Banken ETF Trend (KBE 13W-Momentum)",
                "category": "capacity",
                "source": "yf_momentum",
                "symbol": ["KBE"],
                "invert": False,
                "yoy": False,
                "params": {"window_weeks": 13},
            },
            {
                "id": "bnk_prc_1",
                "name": "10Y-2Y Treasury Yield Spread (FRED)",
                "category": "price",
                "source": "fred",
                "symbol": "T10Y2Y",
                "invert": False,
                "yoy": False,
                "params": {},
            },
            {
                "id": "bnk_prc_2",
                "name": "Net Margin / ROE Trend (JPM, BAC, KBE)",
                "category": "price",
                "source": "yf_margin",
                "symbol": ["JPM", "BAC", "KBE"],
                "invert": False,
                "yoy": False,
                "params": {"margin_type": "net"},
            },
        ],
    },
}