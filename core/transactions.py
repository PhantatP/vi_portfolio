# core/transactions.py
from .db import get_connection
from .fx import fetch_usd_thb_rate
from .symbols import detect_asset_profile
import pandas as pd
import numpy as np

def upsert_asset_if_missing(ticker, name=None, country=None, currency=None, type_="stock", sector=None, industry=None, tags=None):
    """
    Ensure an asset row exists, auto-detecting type/currency/name via Yahoo.
    If the asset already exists, only fill missing fields (COALESCE).
    """
    det = detect_asset_profile(ticker)
    name     = name     or det.get("name")
    country  = country  or det.get("country")
    currency = currency or det.get("currency")
    type_    = type_    or det.get("type")
    sector   = sector   or det.get("sector")
    industry = industry or det.get("industry")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO assets (ticker, name, country, currency, type, sector, industry, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          name=COALESCE(excluded.name, name),
          country=COALESCE(excluded.country, country),
          currency=COALESCE(excluded.currency, currency),
          type=COALESCE(excluded.type, type),
          sector=COALESCE(excluded.sector, sector),
          industry=COALESCE(excluded.industry, industry),
          tags=COALESCE(excluded.tags, tags)
        """,
        (ticker, name, country, currency, type_, sector, industry, tags)
    )
    conn.commit()
    conn.close()

def add_transaction(
    *,
    ticker: str,
    broker: str,
    trade_date: str,            # "YYYY-MM-DD"
    side: str,                  # "buy" / "sell"
    quantity: float,
    price_per_share: float = None,   # per-share price (USD for US stocks/ETFs typically)
    price_ccy: str = "USD",          # currency of price_per_share
    fee: float = 0.0,
    fee_ccy: str | None = None,      # "USD" / "THB"; if None -> same as price_ccy
    thb_amount: float | None = None, # actual THB charged by broker/app
    usd_amount: float | None = None, # total USD notionals (qty*price); optional
    fx_thb_per_usd: float | None = None  # explicit FX override
) -> None:
    """
    Record a transaction linked to an (auto-upserted) asset.
    Stores both per-share price (in price_ccy) and optional THB total.
    """
    side = side.lower().strip()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")

    # ensure asset row first
    upsert_asset_if_missing(ticker, currency=price_ccy)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM assets WHERE ticker = ?", (ticker,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise RuntimeError("Failed to upsert asset for this ticker.")
    asset_id = row[0]

    if fee_ccy is None:
        fee_ccy = price_ccy

    # convenience: compute usd_amount if not provided
    if usd_amount is None and price_per_share is not None and price_ccy.upper().startswith("USD"):
        usd_amount = float(price_per_share) * float(quantity)

    # infer FX if not provided and we have both THB and USD notionals
    if fx_thb_per_usd is None and thb_amount and usd_amount and float(usd_amount) != 0.0:
        fx_thb_per_usd = float(thb_amount) / float(usd_amount)

    cur.execute(
        """
        INSERT INTO transactions
          (asset_id, broker, trade_date, side, quantity, price, fee, currency,
           price_ccy, thb_amount, usd_amount, fx_thb_per_usd, fee_ccy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id, broker, trade_date, side, float(quantity),
            float(price_per_share) if price_per_share is not None else None,
            float(fee) if fee is not None else 0.0,
            price_ccy,  # legacy mirror
            price_ccy, thb_amount, usd_amount, fx_thb_per_usd, fee_ccy
        )
    )
    conn.commit()
    conn.close()

def _transactions_df() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT t.*, a.ticker, a.currency AS asset_currency
        FROM transactions t
        JOIN assets a ON a.id = t.asset_id
        ORDER BY t.trade_date, t.id
        """,
        conn
    )
    conn.close()
    return df

def _thb_notional_for_row(row: pd.Series, fallback_fx: float | None) -> float:
    """
    THB notional per transaction. Priority:
      1) thb_amount if provided
      2) usd_amount * fx
      3) qty*price (USD)*fx  or qty*price (THB)
    Then add fee (converted if needed).
    Ensures fx is always available and NaNs don’t zero-out math.
    """
    # Pick an FX: explicit -> fallback -> hard default
    fx = row.get("fx_thb_per_usd")
    if pd.isna(fx) or not fx:
        fx = fallback_fx if (fallback_fx and not pd.isna(fallback_fx)) else 35.0

    qty = row.get("quantity")
    price = row.get("price")
    fee = row.get("fee")
    fee_ccy = (row.get("fee_ccy") or row.get("currency") or "").upper()
    price_ccy = (row.get("price_ccy") or row.get("currency") or "").upper()

    # Normalize numerics
    qty = float(qty) if pd.notna(qty) else 0.0
    price = float(price) if pd.notna(price) else None
    fee = float(fee) if pd.notna(fee) else 0.0

    thb_amount = row.get("thb_amount")
    usd_amount = row.get("usd_amount")
    has_thb = pd.notna(thb_amount)
    has_usd = pd.notna(usd_amount)

    # Base notional
    if has_thb:
        base_thb = float(thb_amount)
    elif has_usd:
        base_thb = float(usd_amount) * float(fx)
    elif qty and (price is not None):
        if price_ccy.startswith("USD"):
            base_thb = qty * price * float(fx)
        else:
            base_thb = qty * price  # treat as THB
    else:
        base_thb = 0.0

    # Fees
    if fee:
        if fee_ccy.startswith("USD"):
            base_thb += fee * float(fx)
        else:
            base_thb += fee

    return float(base_thb)

def rebuild_holdings_from_transactions() -> pd.DataFrame:
    """
    Rebuild holdings (qty + THB avg cost) per (ticker, broker) using moving-average:
      BUY:  new_avg = (prev_cost + buy_thb_total) / (prev_qty + buy_qty)
      SELL: qty -= sell_qty (avg unchanged)
    Writes holdings with currency='THB' and returns a summary DataFrame.
    """
    tx = _transactions_df()
    if tx.empty:
        return pd.DataFrame(columns=["ticker","broker","quantity","avg_cost_thb_per_unit"])
        # Make sure numeric columns are actually numeric
    for col in ["quantity", "price", "fee", "thb_amount", "usd_amount", "fx_thb_per_usd"]:
        if col in tx.columns:
            tx[col] = pd.to_numeric(tx[col], errors="coerce")

    fallback_fx = fetch_usd_thb_rate()
    tx["_thb_notional"] = tx.apply(lambda r: _thb_notional_for_row(r, fallback_fx), axis=1)

    results = []
    for (ticker, broker), g in tx.groupby(["ticker", "broker"]):
        qty = 0.0
        avg_thb = 0.0
        for _, r in g.sort_values(["trade_date", "id"]).iterrows():
            side = str(r["side"]).lower().strip()
            q = float(r["quantity"]) if pd.notna(r["quantity"]) else 0.0
            thb = float(r["_thb_notional"]) if pd.notna(r["_thb_notional"]) else 0.0
            if side == "buy":
                new_qty = qty + q
                if new_qty <= 0:
                    qty, avg_thb = 0.0, 0.0
                else:
                    total_cost = (avg_thb * qty) + thb
                    avg_thb = total_cost / new_qty
                    qty = new_qty
            elif side == "sell":
                qty = max(0.0, qty - q)
        results.append({"ticker": ticker, "broker": broker, "quantity": qty, "avg_cost_thb_per_unit": avg_thb})

    pos = pd.DataFrame(results)

    # sync holdings table
    conn = get_connection()
    cur = conn.cursor()
    for _, row in pos.iterrows():
        cur.execute("SELECT id FROM assets WHERE ticker = ?", (row["ticker"],))
        a = cur.fetchone()
        if not a:
            continue
        asset_id = a[0]
        cur.execute("DELETE FROM holdings WHERE asset_id = ? AND broker = ?", (asset_id, row["broker"]))
        if row["quantity"] > 0:
            cur.execute(
                "INSERT INTO holdings (asset_id, broker, quantity, avg_price, currency) VALUES (?, ?, ?, ?, 'THB')",
                (asset_id, row["broker"], float(row["quantity"]), float(row["avg_cost_thb_per_unit"]))
            )
    conn.commit()
    conn.close()
    return pos
