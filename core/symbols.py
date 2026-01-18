# core/symbols.py
import re
import yfinance as yf

# Simple exchange suffix → currency hints
SUFFIX_CCY = {
    ".BK": "THB",   # SET Thailand
    ".TO": "CAD",   # Toronto
    ".L":  "GBP",   # London
    ".SI": "SGD",   # Singapore
    ".HK": "HKD",   # Hong Kong
    ".AX": "AUD",   # Australia
    ".NZ": "NZD",   # New Zealand
    ".KS": "KRW",   # Korea
    ".TW": "TWD",   # Taiwan
    ".SS": "CNY",   # Shanghai
    ".SZ": "CNY",   # Shenzhen
}

QUOTE_TYPE_TO_TYPE = {
    "ETF": "etf",
    "EQUITY": "stock",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
    "INDEX": "index",
}

def _infer_currency_from_ticker(t: str) -> str | None:
    if not t:
        return None
    t = t.upper()
    # Crypto tickers like BTC-USD
    if re.match(r".+\-USD$", t):
        return "USD"
    for suf, ccy in SUFFIX_CCY.items():
        if t.endswith(suf):
            return ccy
    # Default for plain US symbols
    return "USD"

def _infer_type_from_ticker(t: str) -> str | None:
    t = (t or "").upper()
    if re.match(r".+\-USD$", t):
        return "crypto"
    return None  # let Yahoo decide

def detect_asset_profile(ticker: str) -> dict:
    """
    Returns best-effort profile:
      { 'ticker','name','country','currency','type','sector','industry' }
    Uses yfinance info/fast_info/quoteType with sensible fallbacks.
    """
    t = (ticker or "").strip()
    prof = {
        "ticker": t,
        "name": None,
        "country": None,
        "currency": None,
        "type": None,
        "sector": None,
        "industry": None,
    }
    if not t:
        return prof

    yt = yf.Ticker(t)
    info = {}
    try:
        info = yt.info or {}
    except Exception:
        info = {}

    # quoteType & currency from Yahoo if available
    quote_type = (info.get("quoteType") or info.get("securityType") or "").upper()
    prof["type"] = QUOTE_TYPE_TO_TYPE.get(quote_type) or _infer_type_from_ticker(t) or "stock"

    # currency preference: info.currency → fast_info.last_price currency is not provided, so rely on info or suffix
    prof["currency"] = info.get("currency") or _infer_currency_from_ticker(t)

    # name/sector/industry/country
    prof["name"] = info.get("longName") or info.get("shortName")
    prof["sector"] = info.get("sector")
    prof["industry"] = info.get("industry")
    prof["country"] = info.get("country")

    return prof
