import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd

from core.db_init import init_db
from core.db import get_connection
from core.portfolio import build_portfolio_view_thb, get_holdings_df
from core.research import get_basic_info
from core.transactions import add_transaction, rebuild_holdings_from_transactions, upsert_asset_if_missing
from core.symbols import detect_asset_profile

st.set_page_config(page_title="VI Dashboard (THB-aware)", layout="wide")
init_db()

def list_assets_df():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT id, ticker, name, country, currency, type, sector, industry FROM assets ORDER BY ticker",
        conn
    )
    conn.close()
    return df

def list_transactions_df():
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT t.id, a.ticker, t.broker, t.trade_date, t.side, t.quantity, t.price, t.fee,
               t.price_ccy, t.thb_amount, t.usd_amount, t.fx_thb_per_usd, t.fee_ccy
        FROM transactions t
        JOIN assets a ON a.id = t.asset_id
        ORDER BY t.trade_date DESC, t.id DESC
        """,
        conn
    )
    conn.close()
    return df

tabs = st.tabs([
    "📊 Dashboard (THB)",
    "💸 Add Transaction",
    "🔁 Rebuild from Transactions",
    "🧠 Research (beta)"
])

with tabs[0]:
    df, total = build_portfolio_view_thb()
    st.metric("Total Portfolio Value (THB)", f"{total:,.2f}")
    if df.empty:
        st.info("No holdings yet. Add transactions, then rebuild.")
    else:
        st.dataframe(
            df[[
                "ticker","broker","quantity",
                "price_thb","avg_cost_thb","value_thb",
                "unrealized_pl_thb","unrealized_pl_pct","weight"
            ]].rename(columns={
                "price_thb":"Last Price (THB)",
                "avg_cost_thb":"Avg Cost (THB)",
                "value_thb":"Value (THB)",
                "unrealized_pl_thb":"Unrealized P/L (THB)",
                "unrealized_pl_pct":"Unrealized P/L (%)"
            }),
            width='stretch'
        )
    st.divider()
    st.subheader("Assets (auto-created via transactions)")
    st.dataframe(list_assets_df(), width='stretch')

with tabs[1]:
    st.subheader("Add Transaction (auto-detect ticker type & currency)")

    # live detection preview
    tkr_preview = st.text_input("Ticker (preview detection)", placeholder="e.g. JEPQ, AAPL, CPALL.BK, BTC-USD").strip()
    if tkr_preview:
        det = detect_asset_profile(tkr_preview)
        st.info(
            f"Detected → type: **{det.get('type')}**, currency: **{det.get('currency')}**"
            + (f", name: {det.get('name')}" if det.get('name') else "")
        )

    with st.form("tx_form", clear_on_submit=True):
        c0, c1, c2, c3 = st.columns(4)
        ticker     = c0.text_input("Ticker *").strip()
        broker     = c1.text_input("Broker *", placeholder="SCB, KS, IBKR, Dime").strip()
        trade_date = c2.text_input("Trade date * (YYYY-MM-DD)").strip()
        side       = c3.selectbox("Side *", ["buy","sell"])

        st.markdown("**Per-share price** (usually USD for US symbols)")
        c4, c5, c6 = st.columns(3)
        quantity        = c4.number_input("Quantity *", min_value=0.0, step=1.0, format="%.6f")
        price_per_share = c5.number_input("Price per share", min_value=0.0, step=0.0001, format="%.6f")
        fee             = c6.number_input("Fee (optional)", min_value=0.0, step=0.01, format="%.4f")

        c7, c8, c9 = st.columns(3)
        price_ccy = c7.selectbox("Price currency", ["USD","THB"], index=0)
        fee_ccy   = c8.selectbox("Fee currency", ["USD","THB"], index=0)
        fx_input  = c9.text_input("FX override (THB per USD, optional)", placeholder="e.g. 36.25").strip()
        fx_value  = float(fx_input) if fx_input else None

        st.markdown("**THB you actually paid** (card/broker charge)")
        thb_amount = st.number_input("THB amount (optional but recommended for US buys)", min_value=0.0, step=0.01, format="%.2f")

        submitted = st.form_submit_button("Add Transaction")
        if submitted:
            try:
                if not (ticker and broker and trade_date and side and quantity > 0):
                    st.error("Please fill all required fields.")
                else:
                    # auto-create/update asset with detected type & currency
                    upsert_asset_if_missing(ticker)

                    add_transaction(
                        ticker=ticker,
                        broker=broker,
                        trade_date=trade_date,
                        side=side,
                        quantity=float(quantity),
                        price_per_share=float(price_per_share) if price_per_share>0 else None,
                        price_ccy=price_ccy,
                        fee=float(fee) if fee>0 else 0.0,
                        fee_ccy=fee_ccy,
                        thb_amount=float(thb_amount) if thb_amount>0 else None,
                        usd_amount=(float(quantity)*float(price_per_share)) if price_ccy=="USD" and price_per_share>0 else None,
                        fx_thb_per_usd=fx_value
                    )
                    st.success(f"Transaction added for {ticker} ({side}). Asset auto-upserted.")
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.subheader("Recent Transactions")
    st.dataframe(list_transactions_df(), width='stretch')

with tabs[2]:
    st.subheader("Rebuild Holdings from Transactions")
    st.caption("Recomputes quantity and **THB avg cost** per (ticker, broker).")
    if st.button("Rebuild now"):
        pos = rebuild_holdings_from_transactions()
        st.success("Holdings rebuilt.")
        st.dataframe(pos, width='stretch')

with tabs[3]:
    st.subheader("Research (beta)")
    t = st.text_input("Ticker")
    if t:
        info = get_basic_info(t)
        if not any(info.values()):
            st.warning("No info found. Try a different symbol.")
        else:
            st.json(info)
