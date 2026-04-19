from .db import get_connection
from .portfolio import build_portfolio_view_thb
import pandas as pd
import yfinance as yf
import numpy as np

def update_target_weight(ticker: str, weight: float):
    """Update target weight for an asset."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE assets SET target_weight = ? WHERE ticker = ?", (weight, ticker))
    conn.commit()
    conn.close()

def get_rebalancing_needs():
    """Calculate how much to buy/sell to reach target weights."""
    df, total_val = build_portfolio_view_thb()
    if df.empty:
        return pd.DataFrame()
    
    # Aggregate by ticker (in case of multiple brokers)
    ticker_df = df.groupby("ticker").agg({
        "value_thb": "sum",
        "target_weight": "first",
        "price_thb": "first"
    }).reset_index()
    
    ticker_df["current_weight"] = (ticker_df["value_thb"] / total_val) * 100
    ticker_df["difference_pct"] = ticker_df["target_weight"] - ticker_df["current_weight"]
    ticker_df["diff_value_thb"] = (ticker_df["difference_pct"] / 100) * total_val
    
    # Calculate shares needed (if price is available)
    def calc_shares(row):
        if pd.isna(row["price_thb"]) or row["price_thb"] == 0:
            return 0
        return row["diff_value_thb"] / row["price_thb"]
    
    ticker_df["shares_to_buy"] = ticker_df.apply(calc_shares, axis=1)
    
    return ticker_df

# SMART_PEERS maps sectors/industries to interesting symbols for suggestion
SMART_PEERS = {
    "Technology": {
        "Computer Hardware": ["AAPL", "WDC", "STX", "HPQ", "DELL"],
        "Semiconductors": ["NVDA", "AMD", "TSM", "INTC", "ASML", "AVGO"],
        "Software - Infrastructure": ["MSFT", "ORCL", "SNOW", "PLTR"],
        "Software - Application": ["ADBE", "CRM", "SAP", "INTU"],
    },
    "Consumer Cyclical": {
        "Internet Retail": ["AMZN", "BABA", "EBAY", "PDD", "MELI"],
        "Auto Manufacturers": ["TSLA", "TM", "F", "GM", "RACE"],
        "Footwear & Accessories": ["NKE", "DECK", "SKX"],
    },
    "Financial Services": {
        "Banks - Diversified": ["JPM", "BAC", "WFC", "C"],
        "Asset Management": ["BLK", "BX", "KKR", "TROW"],
        "Credit Services": ["V", "MA", "AXP", "PYPL"],
    },
    "Healthcare": {
        "Drug Manufacturers - General": ["LLY", "JNJ", "PFE", "MRK", "ABBV"],
        "Biotechnology": ["AMGN", "GILD", "REGN", "VRTX"],
    },
    "Communication Services": {
        "Internet Content & Information": ["GOOG", "META", "PINS", "SNAP"],
        "Entertainment": ["NFLX", "DIS", "WBD", "PARA"],
    }
}

def get_smart_picks():
    """Analyze current portfolio and suggest related stocks automatically."""
    df, _ = build_portfolio_view_thb()
    if df.empty:
        # If no holdings, suggest some general big tech as starting point
        return ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]
    
    # 1. Identify top 2 sectors/industries by value
    top_groups = df.groupby(["sector", "industry"]).agg({"value_thb": "sum"}).nlargest(2, "value_thb").reset_index()
    
    suggestions = []
    seen = set(df["ticker"].unique())
    
    for _, row in top_groups.iterrows():
        s = row["sector"]
        i = row["industry"]
        
        # Check industry matches first
        peers = SMART_PEERS.get(s, {}).get(i, [])
        # Fallback to sector-wide if industry not in map
        if not peers:
            all_sector_peers = []
            for industry_peers in SMART_PEERS.get(s, {}).values():
                all_sector_peers.extend(industry_peers)
            peers = all_sector_peers
            
        for p in peers:
            if p not in seen:
                suggestions.append(p)
                
    # Return unique suggestions, limited to a reasonable number
    return list(dict.fromkeys(suggestions))[:8]

def get_recommendations(ticker: str):
    """Fetch related tickers or peers in the same sector."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        sector = info.get("sector")
        if not sector:
            return None
        return sector
    except:
        return None

def get_all_sector_peers():
    """Returns a flat dictionary of sectors and all peers inside them."""
    result = {}
    for sector, industries in SMART_PEERS.items():
        all_peers = []
        for peer_list in industries.values():
            all_peers.extend(peer_list)
        result[sector] = sorted(list(set(all_peers)))
    return result

def get_hierarchical_distribution():
    """Aggregate portfolio value by Sector -> Industry -> Ticker."""
    df, _ = build_portfolio_view_thb() # Changed from get_holdings_df() to build_portfolio_view_thb() to match existing code structure
    if df.empty:
        return pd.DataFrame()
    
    # Fill NAs for hierarchy
    df['sector'] = df['sector'].fillna('Unknown Sector')
    df['industry'] = df['industry'].fillna('Unknown Industry')
    # The original code also filled 'ticker', but the new code doesn't explicitly.
    # Since 'ticker' is used in groupby, pandas will handle NaNs by grouping them.
    # If a specific 'Unknown' ticker is desired, it should be added here.
    # For now, following the provided instruction which omits it.
    
    # Aggregate
    dist = df.groupby(['sector', 'industry', 'ticker'])['value_thb'].sum().reset_index()
    
    # Safety: Ensure values are numeric and non-negative
    dist['value_thb'] = pd.to_numeric(dist['value_thb'], errors='coerce').fillna(0)
    dist = dist[dist['value_thb'] > 0]
    
    return dist
