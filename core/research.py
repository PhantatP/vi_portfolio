# Placeholder for research utilities (we’ll extend later with scoring + notes save/load)
import yfinance as yf

def get_basic_info(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    try:
        info = t.info  # may be sparse for some tickers/markets
    except Exception:
        info = {}
    return {
        "longName": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "summary": info.get("longBusinessSummary"),
        "currency": info.get("currency"),
    }
