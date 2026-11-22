"""
watch_positions.py
Täglicher Wächter für offene Positionen in portfolio.json.
Sendet sofort einen Telegram-Alarm, sobald der Trailing-Stop gerissen wird.
"""

import json
import os
from dotenv import load_dotenv
import yfinance as yf
from config import PORTFOLIO_PATH
import notifier


def main():
    load_dotenv()
    if not os.path.exists(PORTFOLIO_PATH):
        print("Keine portfolio.json gefunden.")
        return

    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        positions = json.load(f)

    if not positions:
        print("Keine offenen Positionen in portfolio.json.")
        return

    for pos in positions:
        ticker = pos["ticker"]
        entry_date = pos["entry_date"]
        entry_price = float(pos["entry_price"])
        stop_pct = float(pos.get("trailing_stop_pct", 0.15))

        df = yf.download(ticker, start=entry_date, progress=False, auto_adjust=True, threads=False)
        if df is None or df.empty:
            continue

        close = df["Close"].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
        curr_price = float(close.iloc[-1])
        peak_price = max(entry_price, float(close.max()))
        stop_price = peak_price * (1.0 - stop_pct)
        pnl_pct = ((curr_price / entry_price) - 1.0) * 100.0

        print(f"{ticker}: Kurs={curr_price:.2f} | Peak={peak_price:.2f} | Stop={stop_price:.2f} | PnL={pnl_pct:+.1f}%")

        if curr_price <= stop_price:
            msg = (
                f"🚨 <b>TRAILING-STOP AUSGELÖST – {ticker}</b>\n"
                f"• Aktueller Kurs: <b>{curr_price:.2f}</b> (Stop war {stop_price:.2f})\n"
                f"• Hoch seit Kauf: {peak_price:.2f} (-{stop_pct*100:.0f}%)\n"
                f"• Offene Rendite: <b>{pnl_pct:+.1f}%</b>"
            )
            notifier.send_telegram_message(msg)


if __name__ == "__main__":
    main()
