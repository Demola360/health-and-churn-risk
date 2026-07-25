"""
Day 1 - Step 1: Market data pull
Pulls daily OHLCV data for 8 major banking sector tickers as a "market health"
proxy. The idea: broader banking-sector stress/volatility is one signal that
can correlate with client churn risk in a financial-services book of business.

Tickers: mix of US and UK banks, since the target job market is UK-based.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime

BANK_TICKERS = [
    "JPM",      # JPMorgan Chase (US)
    "BAC",      # Bank of America (US)
    "WFC",      # Wells Fargo (US)
    "C",        # Citigroup (US)
    "GS",       # Goldman Sachs (US)
    "MS",       # Morgan Stanley (US)
    "HSBC",     # HSBC (UK, ADR)
    "BCS",      # Barclays (UK, ADR)
]

PERIOD = "1y"       # how far back to pull
INTERVAL = "1d"      # daily granularity


def fetch_market_data(tickers=BANK_TICKERS, period=PERIOD, interval=INTERVAL) -> pd.DataFrame:
    """Fetch OHLCV data for each ticker and return one tidy long-format DataFrame."""
    all_rows = []

    for ticker in tickers:
        print(f"Fetching {ticker}...")
        data = yf.Ticker(ticker).history(period=period, interval=interval)

        if data.empty:
            print(f"  WARNING: no data returned for {ticker}, skipping.")
            continue

        data = data.reset_index()
        data["ticker"] = ticker

        # Daily return and a simple rolling volatility measure — these are the
        # two fields the SQL layer will use to build the "market stress" signal.
        data["daily_return"] = data["Close"].pct_change()
        data["volatility_10d"] = data["daily_return"].rolling(10).std()

        all_rows.append(data)

    combined = pd.concat(all_rows, ignore_index=True)

    # Normalise column names for Snowflake (upper/lower case can bite you later)
    combined = combined.rename(columns={
        "Date": "trade_date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    combined = combined[[
        "ticker", "trade_date", "open", "high", "low", "close",
        "volume", "daily_return", "volatility_10d"
    ]]

    return combined


if __name__ == "__main__":
    df = fetch_market_data()
    out_path = "market_data.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} rows for {df['ticker'].nunique()} tickers to {out_path}")
    print(f"Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
