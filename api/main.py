from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import date as dt_date
import pandas as pd
import sys
import os

# Ensure the core/ directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio import build_portfolio_view_thb, get_holdings_df
from core.analysis import get_rebalancing_needs, get_hierarchical_distribution, get_smart_picks, get_all_sector_peers
from core.research import get_basic_info, get_price_history, get_income_funnel
from core.transactions import add_transaction, rebuild_holdings_from_transactions, upsert_asset_if_missing

app = FastAPI(title="VI Portfolio API")

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
        top_gainer = df.nlargest(1, 'unrealized_pl_pct').iloc[0].to_dict() if not df.empty else None
        worst_loser = df.nsmallest(1, 'unrealized_pl_pct').iloc[0].to_dict() if not df.empty else None
        
        return {
            "total_val": total_val,
            "total_cost": total_cost,
            "total_profit": total_profit,
            "profit_pct": (total_profit / total_cost * 100) if total_cost > 0 else 0,
            "top_gainer": top_gainer,
            "worst_loser": worst_loser,
            "allocation": df.set_index("ticker")["value_thb"].to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/holdings")
def get_holdings():
    try:
        df, _ = build_portfolio_view_thb()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis/distribution")
def get_distribution():
    try:
        df = get_hierarchical_distribution()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis/rebalance")
def get_rebalance():
    try:
        df = get_rebalancing_needs()
        return df.to_dict(orient="records")
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
        history = get_price_history(ticker).to_dict(orient="records")
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
    quantity: float
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

@app.post("/api/ocr/parse")
async def ocr_parse(file: UploadFile = File(...)):
    try:
        from core.ocr_parser import parse_dime_image
        image_bytes = await file.read()
        parsed = parse_dime_image(image_bytes)
        return {"transactions": parsed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BulkTransactionIn(BaseModel):
    transactions: List[TransactionIn]

@app.post("/api/ocr/import")
def ocr_import(body: BulkTransactionIn):
    try:
        count = 0
        for tx in body.transactions:
            ticker = tx.ticker.strip().upper()
            if not ticker:
                continue
            upsert_asset_if_missing(ticker)
            add_transaction(
                ticker=ticker,
                broker=tx.broker,
                trade_date=tx.trade_date or str(dt_date.today()),
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
            count += 1
        rebuild_holdings_from_transactions()
        return {"status": "ok", "imported": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/assets")
def get_assets():
    try:
        df = get_holdings_df()
        tickers = df["ticker"].tolist() if not df.empty else []
        return {"tickers": tickers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
