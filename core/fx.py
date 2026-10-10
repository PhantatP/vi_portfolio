from datetime import date, timedelta

import yfinance as yf

from .prices import USD_THB, latest_prices

MAX_STORED_AGE_DAYS = 7  # older means the refresh job stopped; prefer a live rate

def fetch_usd_thb_rate(default: float = 36.0, live: bool = True) -> float:
    """
    Return a reliable USD→THB rate.
    Uses:
      0) latest stored close (core/prices.py), if recent
      1) fast_info.last_price
      2) history Close price
      3) stale stored close
      4) fallback default
    live=False skips 1) and 2). Never returns None.
    """

    # 0) Stored by the price refresh job
    stored = latest_prices([USD_THB])
    stored_rate = float(stored["price"].iloc[0]) if not stored.empty else None
    if stored_rate and date.fromisoformat(stored["as_of"].iloc[0]) >= date.today() - timedelta(days=MAX_STORED_AGE_DAYS):
        return stored_rate
    if not live:
        return stored_rate or default

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

    # 3) Stale stored rate beats a hard-coded one
    if stored_rate:
        return stored_rate

    # 4) Hard fallback
    return default
