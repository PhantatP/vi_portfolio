import yfinance as yf
import pandas as pd
import streamlit as st

@st.cache_data(ttl=3600)
def get_basic_info(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    try:
        info = t.info  # may be sparse for some tickers/markets
    except Exception:
        info = {}
        
    return {
        "ticker": ticker,
        "longName": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "summary": info.get("longBusinessSummary"),
        "currency": info.get("currency"),
        "forwardPE": info.get("forwardPE"),
        "trailingPE": info.get("trailingPE"),
        "marketCap": info.get("marketCap"),
        "beta": info.get("beta"),
        "currentPrice": info.get("currentPrice") or info.get("navPrice"),
        "dividendYield": info.get("dividendYield"),
    }

@st.cache_data(ttl=3600)
def get_price_history(ticker: str, period: str = "1y"):
    """Fetch historical price data for charting."""
    t = yf.Ticker(ticker)
    df = t.history(period=period)
    if df.empty:
        return pd.DataFrame()
    return df.reset_index()

@st.cache_data(ttl=3600)
def get_income_funnel(ticker: str):
    """Fetch recent annual income statement metrics for a waterfall/funnel chart."""
    t = yf.Ticker(ticker)
    try:
        df = t.income_stmt
        if df.empty:
            return {}
            
        latest_col = df.columns[0]
        data = df[latest_col]
        
        def safe_float(val):
            try:
                if val is not None and not pd.isna(val):
                    return float(val)
            except: pass
            return None

        return {
            "Total Revenue": safe_float(data.get("Total Revenue")),
            "Gross Profit": safe_float(data.get("Gross Profit")),
            "Operating Income": safe_float(data.get("Operating Income")),
            "Net Income": safe_float(data.get("Net Income")),
            "Date": str(latest_col.date())
        }
    except Exception:
        return {}
