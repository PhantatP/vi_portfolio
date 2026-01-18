from .db import get_connection
from .fx import fetch_usd_thb_rate
import pandas as pd
import yfinance as yf
import numpy as np
import re

def _normalize_ticker(t: str) -> str:
    return (t or "").strip().upper()

def _pick_price_column(df):
    # df is the multi-column frame from yf.download
    for col in ["Adj Close", "Close"]:
        if col in df.columns:
            return df[col].tail(1)
    # sometimes download returns a single-level Series
    if isinstance(df, pd.Series):
        return df.tail(1)
    return None

def fetch_latest_prices(tickers):
    """
    Stable price fetcher:
    1) Try fast_info.last_price
    2) Try .history Close
    Always returns DataFrame with ['ticker','price'].
    """
    tickers = [t.upper() for t in tickers if t]
    rows = []

    for t in tickers:
        price = None

        # 1) fast_info
        try:
            fi = yf.Ticker(t).fast_info
            lp = fi.get("last_price")
            if lp:
                price = float(lp)
        except Exception:
            pass

        # 2) history close
        if price is None:
            try:
                h = yf.Ticker(t).history(period="1d")
                if "Close" in h.columns and len(h) > 0:
                    price = float(h["Close"].iloc[-1])
            except Exception:
                pass

        if price is not None:
            rows.append({"ticker": t, "price": price})

    # Always return DataFrame with correct columns
    if not rows:
        return pd.DataFrame({ "ticker": tickers, "price": [np.nan]*len(tickers) })

    return pd.DataFrame(rows)

def _infer_currency_from_ticker(ticker: str) -> str:
    """Best-effort currency inference if asset_currency is missing."""
    t = (ticker or "").upper()
    if t.endswith(".BK"):
        return "THB"
    if t.endswith("-USD") or re.match(r"^[A-Z0-9\-]+-USD$", t):
        return "USD"
    # common US symbols (no suffix) default to USD
    return "USD"

def get_holdings_df():
    """
    Load current holdings from database.
    Each row = aggregated position per (asset_id, broker)
    Contains:
        holding_id, ticker, name, country, asset_currency, type, tags,
        broker, quantity, avg_price, holding_currency
    """
    conn = get_connection()
    query = """
    SELECT 
        h.id AS holding_id,
        a.ticker,
        a.name,
        a.country,
        a.currency AS asset_currency,
        a.type,
        a.tags,
        h.broker,
        h.quantity,
        h.avg_price,
        h.currency AS holding_currency
    FROM holdings h
    JOIN assets a ON a.id = h.asset_id
    ORDER BY a.ticker, h.broker;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def build_portfolio_view_thb():
    hold = get_holdings_df()
    if hold.empty:
        return hold, 0.0
    hold["ticker"] = hold["ticker"].astype(str).str.upper()
    prices = fetch_latest_prices(hold["ticker"].unique().tolist())
    if "ticker" not in prices.columns:
        prices = pd.DataFrame({"ticker": hold["ticker"].unique(), "price": pd.NA})
    df = hold.merge(prices, on="ticker", how="left")


    usd_thb = fetch_usd_thb_rate()
    df["usd_thb"] = usd_thb

    # Decide asset currency (fallback if NULL)
    def asset_ccy(row):
        c = row.get("asset_currency")
        if c and isinstance(c, str) and c.strip():
            return c.upper()
        return _infer_currency_from_ticker(row.get("ticker"))
    df["asset_ccy_eff"] = df.apply(asset_ccy, axis=1)

    # Convert last price to THB
    def price_to_thb(row):
        px = row["price"]
        if pd.isna(px):
            return np.nan
        ccy = str(row["asset_ccy_eff"]).upper()
        if ccy.startswith("USD"):
            return float(px) * float(usd_thb) if usd_thb else np.nan
        if ccy.startswith("THB"):
            return float(px)
        # fallback: treat as THB if unknown
        return float(px)
    df["price_thb"] = df.apply(price_to_thb, axis=1)

    # Avg cost already set to THB when we rebuild from transactions (currency='THB')
    def avg_cost_thb(row):
        if str(row["holding_currency"]).upper().startswith("THB"):
            return float(row["avg_price"])
        # If for some reason it's USD, convert
        if str(row["holding_currency"]).upper().startswith("USD") and usd_thb:
            return float(row["avg_price"]) * float(usd_thb)
        return float(row["avg_price"])
    df["avg_cost_thb"] = df.apply(lambda r: avg_cost_thb(r) if pd.notna(r["avg_price"]) else np.nan, axis=1)

    # Values & P/L in THB
    df["value_thb"] = df["quantity"] * df["price_thb"]
    df["cost_thb_total"] = df["quantity"] * df["avg_cost_thb"]
    df["unrealized_pl_thb"] = df["value_thb"] - df["cost_thb_total"]
    df["unrealized_pl_pct"] = np.where(df["cost_thb_total"]>0, df["unrealized_pl_thb"]/df["cost_thb_total"], np.nan)

    total = float(np.nansum(df["value_thb"]))
    df["weight"] = np.where(total>0, df["value_thb"]/total, 0.0)

    # Optional: mark missing prices so UI can warn
    df["price_missing"] = df["price_thb"].isna()

    return df, total
