import yfinance as yf

def fetch_usd_thb_rate(default: float = 36.0) -> float:
    """
    Return a reliable USD→THB rate.
    Uses:
      1) fast_info.last_price  
      2) history Close price  
      3) fallback default  
    Never returns None.
    """

    # 1) Try fast_info (most reliable)
    try:
        fi = yf.Ticker("USDTHB=X").fast_info
        lp = fi.get("last_price")
        if lp:
            return float(lp)
    except Exception:
        pass

    # 2) Try history
    try:
        d = yf.Ticker("USDTHB=X").history(period="1d")
        if "Close" in d.columns and len(d) > 0:
            return float(d["Close"].iloc[-1])
    except Exception:
        pass

    # 3) Hard fallback
    return default
