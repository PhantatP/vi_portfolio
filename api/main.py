from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
from datetime import date as dt_date
import math
import pandas as pd
import sys
import os

# Ensure the core/ directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio import build_portfolio_view_thb, get_holdings_df
from core.analysis import get_rebalancing_needs, get_hierarchical_distribution, get_smart_picks, get_all_sector_peers
from core.research import get_basic_info, get_price_history, get_income_funnel
from core.transactions import add_transaction, rebuild_holdings_from_transactions, upsert_asset_if_missing
from api.mcp_server import mcp, mcp_app

def _clean(obj):
    """Recursively replace NaN/inf with None so JSON serialization never fails."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj

def _df_records(df: pd.DataFrame):
    return _clean(df.to_dict(orient="records"))

@asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():  # a mounted app's own lifespan doesn't run, so start MCP here
        yield

app = FastAPI(title="VI Portfolio API", lifespan=lifespan)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "online", "app": "VI Portfolio API"}

@app.get("/api/dashboard")
def get_dashboard():
    try:
        df, total_val = build_portfolio_view_thb()
        if df.empty:
            return {"total_val": 0, "total_cost": 0, "total_profit": 0, "profit_pct": 0, "top_gainer": None, "worst_loser": None, "holdings": [], "allocation": {}, "stats": {}}
        
        total_cost = df["cost_thb_total"].sum()
        total_profit = df["unrealized_pl_thb"].sum()
        
        # Mini stats
        top_gainer = _clean(df.nlargest(1, 'unrealized_pl_pct').iloc[0].to_dict()) if not df.empty else None
        worst_loser = _clean(df.nsmallest(1, 'unrealized_pl_pct').iloc[0].to_dict()) if not df.empty else None

        return _clean({
            "total_val": total_val,
            "total_cost": total_cost,
            "total_profit": total_profit,
            "profit_pct": (total_profit / total_cost * 100) if total_cost > 0 else 0,
            "top_gainer": top_gainer,
            "worst_loser": worst_loser,
            "allocation": df.set_index("ticker")["value_thb"].to_dict()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/holdings")
def get_holdings():
    try:
        df, _ = build_portfolio_view_thb()
        return _df_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis/distribution")
def get_distribution():
    try:
        df = get_hierarchical_distribution()
        return _df_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis/rebalance")
def get_rebalance():
    try:
        df = get_rebalancing_needs()
        return _df_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/discovery/smart-picks")
def get_smart_discovery():
    return get_smart_picks()

@app.get("/api/discovery/sectors")
def get_sectors():
    return get_all_sector_peers()

@app.get("/api/research/stock/{ticker}")
def get_stock_research(ticker: str):
    try:
        info = get_basic_info(ticker)
        history = _df_records(get_price_history(ticker))
        funnel = get_income_funnel(ticker)
        return {
            "info": info,
            "history": history,
            "funnel": funnel
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TransactionIn(BaseModel):
    ticker: str
    side: str
    quantity: float = 0.0
    price_per_share: Optional[float] = None
    price_ccy: str = "THB"
    broker: str = "Other"
    trade_date: Optional[str] = None
    fee: float = 0.0
    fee_ccy: Optional[str] = None
    thb_amount: Optional[float] = None
    usd_amount: Optional[float] = None
    fx_thb_per_usd: Optional[float] = None

@app.post("/api/transactions")
def post_transaction(tx: TransactionIn):
    try:
        trade_date = tx.trade_date or str(dt_date.today())
        ticker = tx.ticker.strip().upper()
        upsert_asset_if_missing(ticker)
        add_transaction(
            ticker=ticker,
            broker=tx.broker,
            trade_date=trade_date,
            side=tx.side,
            quantity=tx.quantity,
            price_per_share=tx.price_per_share,
            price_ccy=tx.price_ccy,
            fee=tx.fee,
            fee_ccy=tx.fee_ccy,
            thb_amount=tx.thb_amount,
            usd_amount=tx.usd_amount,
            fx_thb_per_usd=tx.fx_thb_per_usd,
        )
        rebuild_holdings_from_transactions()
        return {"status": "ok", "ticker": ticker}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/transactions")
def debug_transactions():
    from core.db import get_connection
    import math
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.ticker, t.trade_date, t.side, t.quantity, t.price, t.price_ccy,
               t.thb_amount, t.usd_amount, t.fx_thb_per_usd
        FROM transactions t JOIN assets a ON a.id = t.asset_id
        ORDER BY t.trade_date DESC LIMIT 50
    """)
    cols = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        row = {}
        for k, v in zip(cols, r):
            row[k] = None if (isinstance(v, float) and math.isnan(v)) else v
        rows.append(row)
    conn.close()
    return rows

@app.get("/api/assets")
def get_assets():
    try:
        df = get_holdings_df()
        tickers = df["ticker"].tolist() if not df.empty else []
        return {"tickers": tickers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import/dime/sync")
def dime_sync(dry_run: bool = False):
    """Fetch new Dime PDFs from Gmail and import them. dry_run=true reports without writing."""
    from core.dime_import import sync_from_gmail
    try:
        return sync_from_gmail(dry_run=dry_run)
    except RuntimeError as e:  # missing password / Gmail token
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/import/dime/reconcile")
def dime_reconcile():
    """Compare DB share counts with the latest imported Dime monthly statement."""
    from core.dime_import import latest_statement, reconcile
    statement = latest_statement()
    if statement is None:
        raise HTTPException(status_code=404, detail="No Dime monthly statement imported yet")
    return reconcile(statement)

# MCP for AI agents at /mcp: add its single route rather than mounting the app at "/", which would
# swallow FastAPI's trailing-slash redirects and 405s for every other path.
app.router.routes.extend(mcp_app.routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
