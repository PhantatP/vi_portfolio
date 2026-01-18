import sys
from pathlib import Path
import datetime

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import numpy as np

from core.db_init import init_db
from core.db import get_connection
from core.portfolio import build_portfolio_view_thb, get_holdings_df
from core.research import get_basic_info
from core.transactions import add_transaction, rebuild_holdings_from_transactions, upsert_asset_if_missing
from core.symbols import detect_asset_profile
from core.ocr_parser import parse_dime_image

# -----------------------------------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="VI Portfolio",
    page_icon="📈",
    layout="centered", # Better for mobile than 'wide'
    initial_sidebar_state="collapsed"
)

# Custom CSS for Mobile Tweaks
st.markdown("""
<style>
    /* Bigger buttons for thumb-tapping */
    div.stButton > button:first-child {
        min-height: 50px;
        width: 100%;
        border-radius: 12px;
        font-weight: 600;
    }
    /* Hide default menu to save space */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Metrics clearer */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
</style>
""", unsafe_allow_html=True)

init_db()

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def load_data():
    df, total = build_portfolio_view_thb()
    return df, total

# -----------------------------------------------------------------------------
# TABS
# -----------------------------------------------------------------------------
# "Add" is first for quick access
tab_add, tab_dash, tab_holdings, tab_more = st.tabs([
    "💸 Add", "📊 Dash", "💼 Port", "⚙️ More"
])

# -----------------------------------------------------------------------------
# TAB 1: ADD TRANSACTION (Mobile First)
# -----------------------------------------------------------------------------
with tab_add:
    st.markdown("### Quick Trade")
    
    with st.container():
        # Quick Ticker Detection
        ticker = st.text_input("Ticker Symbol", placeholder="e.g. CPALL.BK, AAPL").strip().upper()
        det = {}
        
        if ticker:
            det = detect_asset_profile(ticker)
            if det.get('type'):
                 st.caption(f"✨ {det.get('name') or ticker} • {det.get('type')} • {det.get('currency')}")
        
        # Big Side Selector
        c1, c2 = st.columns(2)
        side = c1.radio("Side", ["buy", "sell"], label_visibility="collapsed", horizontal=True)
        is_buy = side == "buy"
        
        # Primary Inputs
        c3, c4 = st.columns(2)
        qty = c3.number_input("Quantity", min_value=0.0, step=1.0, format="%.4f")
        price = c4.number_input("Price / Share", min_value=0.0, step=0.01, format="%.2f")
        
        # Optional Details (Expander to keep UI clean)
        with st.expander("More Options (Date, Fee, FX)", expanded=False):
            trade_date = st.date_input("Date", datetime.date.today())
            broker = st.selectbox("Broker", ["SCB", "Dime", "IBKR", "Bitkub", "Binance", "Other"])
            
            c5, c6 = st.columns(2)
            fee = c5.number_input("Fee", min_value=0.0, step=1.0)
            currency = c6.selectbox("Currency", ["THB", "USD"], index=0 if (det.get('currency') or 'THB') == 'THB' else 1)
            
            # Advanced FX
            fx_rate = None
            if currency == "USD":
                fx_rate = st.number_input("FX Rate (THB/USD)", min_value=0.0, value=34.5, step=0.1)

        # Submit Button
        btn_label = f"🔥 {side.upper()} {ticker}" if ticker else "Submit"
        if st.button(btn_label, use_container_width=True, type="primary"):
            if not ticker or qty <= 0:
                st.error("Need Ticker & Qty")
            else:
                try:
                    upsert_asset_if_missing(ticker)
                    add_transaction(
                        ticker=ticker,
                        broker=broker,
                        trade_date=str(trade_date),
                        side=side,
                        quantity=qty,
                        price_per_share=price if price > 0 else None,
                        price_ccy=currency,
                        fee=fee,
                        fx_thb_per_usd=fx_rate
                    )
                    st.success(f"✅ Saved: {side.upper()} {ticker}")
                    # Trigger rebuild immediately to keep stats fresh
                    rebuild_holdings_from_transactions()
                except Exception as e:
                    st.error(f"Error: {e}")

    # -------------------------------------------------------------------------
    # BULK / OCR UPLOAD
    # -------------------------------------------------------------------------
    with st.expander("📸 Scan Image (Dime)", expanded=False):
        uploaded_file = st.file_uploader("Upload Screenshot", type=["png", "jpg", "jpeg"])
        if uploaded_file is not None:
            with st.spinner("Reading Image..."):
                 try:
                     image_bytes = uploaded_file.read()
                     parsed = parse_dime_image(image_bytes)
                     
                     if not parsed:
                         st.warning("No transactions found.")
                     else:
                         # Show as editable dataframe
                         # Prepare DF 
                         ocr_df = pd.DataFrame(parsed)
                         
                         # Check columns are valid for editor
                         desired_cols = ["side", "ticker", "quantity", "price", "price_currency", "total_amount", "amount_currency", "trade_date"]
                         # Ensure cols exist
                         for c in desired_cols:
                             if c not in ocr_df.columns:
                                 ocr_df[c] = None
                         
                         ocr_df = ocr_df[desired_cols] # reorder
                         
                         st.info(f"Found {len(ocr_df)} items. Please review/edit before saving.")
                         
                         edited_df = st.data_editor(ocr_df, use_container_width=True, num_rows="dynamic")
                         
                         if st.button("Confirm Import", type="primary"):
                             count_success = 0
                             for idx, row in edited_df.iterrows():
                                 side_val = str(row["side"]).lower()
                                 if side_val not in ("buy", "sell"):
                                     st.warning(f"Skipping row {idx}: Side '{side_val}' not supported yet (only buy/sell).")
                                     continue
                                 
                                 try:
                                     tck = str(row["ticker"]).strip().upper()
                                     if not tck or tck == "UNKNOWN":
                                         st.warning(f"Skipping row {idx}: Invalid Ticker")
                                         continue
                                     
                                     # Convert Nones
                                     qty_val = float(row["quantity"]) if pd.notnull(row["quantity"]) else 0.0
                                     price_val = float(row["price"]) if pd.notnull(row["price"]) else None
                                     amt_val = float(row["total_amount"]) if pd.notnull(row["total_amount"]) else None
                                     date_val = str(row["trade_date"]) if pd.notnull(row["trade_date"]) else str(datetime.date.today())
                                     
                                     p_ccy = str(row["price_currency"] or "USD").upper()
                                     a_ccy = str(row["amount_currency"] or "THB").upper()

                                     # Ensure asset exists with CORRECT price currency
                                     upsert_asset_if_missing(tck, currency=p_ccy)
                                     
                                     # add_transaction logic
                                     add_transaction(
                                         ticker=tck,
                                         broker="Dime", 
                                         trade_date=date_val,
                                         side=side_val,
                                         quantity=qty_val,
                                         price_per_share=price_val,
                                         price_ccy=p_ccy,
                                         thb_amount=(amt_val if a_ccy == "THB" else None),
                                         usd_amount=(amt_val if a_ccy == "USD" else None)
                                     )
                                     count_success += 1
                                 except Exception as e:
                                     st.error(f"Error row {idx}: {e}")
                             
                             if count_success > 0:
                                 st.success(f"Successfully imported {count_success} transactions!")
                                 rebuild_holdings_from_transactions()
                                 
                 except Exception as e:
                     st.error(f"OCR Failed: {e}")

# -----------------------------------------------------------------------------
# TAB 2: DASHBOARD
# -----------------------------------------------------------------------------
with tab_dash:
    df, total_val = load_data()
    
    # Hero Metric
    st.metric("Net Worth (THB)", f"{total_val:,.0f}", delta=None)
    
    if not df.empty:
        # Real Cost and Real Profit
        total_cost = df["cost_thb_total"].sum()
        total_profit = df["unrealized_pl_thb"].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Real Cost (THB)", f"{total_cost:,.0f}")
        c2.metric("Real Profit (THB)", f"{total_profit:,.0f}", delta=f"{(total_profit/total_cost if total_cost > 0 else 0)*100:.1f}%")

        st.divider()

        # Mini Stats
        top_gainer = df.nlargest(1, 'unrealized_pl_pct').iloc[0] if not df.empty else None
        worst_loser = df.nsmallest(1, 'unrealized_pl_pct').iloc[0] if not df.empty else None
        
        c1, c2 = st.columns(2)
        if top_gainer is not None:
            c1.metric("🚀 Top Asset", top_gainer['ticker'], f"+{top_gainer['unrealized_pl_pct']*100:.1f}%")
        if worst_loser is not None:
            c2.metric("🔻 Lagging", worst_loser['ticker'], f"{worst_loser['unrealized_pl_pct']*100:.1f}%")

        st.divider()
        
        # Mobile Chart (Donut)
        st.markdown("### Allocation")
        st.bar_chart(df.set_index("ticker")["value_thb"])

# -----------------------------------------------------------------------------
# TAB 3: PORTFOLIO LIST
# -----------------------------------------------------------------------------
with tab_holdings:
    st.markdown("### Your Holdings")
    
    df, _ = load_data()
    if df.empty:
        st.info("No assets found.")
    else:
        # Card View for Mobile
        for i, row in df.iterrows():
            with st.container():
                c1, c2 = st.columns([2, 1])
                c1.markdown(f"**{row['ticker']}**")
                c1.caption(f"{row['quantity']} shares • Avg {row['avg_cost_thb']:.2f}")
                
                pl_color = "green" if row['unrealized_pl_thb'] >= 0 else "red"
                c2.markdown(f"<div style='text-align:right; color:{pl_color}; font-weight:bold;'>{row['unrealized_pl_pct']*100:+.1f}%</div>", unsafe_allow_html=True)
                c2.caption(f"{row['value_thb']:,.0f} ฿")

                # Real Cost & Profit Detail
                c1.caption(f"Cost: {row['cost_thb_total']:,.2f} ฿")
                c2.markdown(f"<div style='text-align:right; color:{pl_color}; font-size: 0.8rem;'>{row['unrealized_pl_thb']:+,.2f} ฿</div>", unsafe_allow_html=True)
                
            st.divider()

# -----------------------------------------------------------------------------
# TAB 4: MORE
# -----------------------------------------------------------------------------
with tab_more:
    st.markdown("### System Actions")
    
    if st.button("🔄 Rebuild All Holdings", use_container_width=True):
        rebuild_holdings_from_transactions()
        st.success("Database recalculated from transactions.")

    if st.button("🛠️ Fix US Asset Currencies", help="Fixes assets incorrectly marked as THB", use_container_width=True):
        from core.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        # Correct assets that should be USD (no .BK suffix) but are currently THB
        cur.execute("""
            UPDATE assets 
            SET currency = 'USD' 
            WHERE ticker NOT LIKE '%.BK' AND currency = 'THB'
        """)
        count = cur.rowcount
        conn.commit()
        conn.close()
        rebuild_holdings_from_transactions()
        st.success(f"Corrected {count} assets. Portfolio rebuilt.")

    with st.expander("🔗 Merge / Rename Tickers", expanded=False):
        st.caption("Change all historical transactions from one symbol to another. Useful for fixing OCR errors like JEPO → JEPQ.")
        col_old, col_new = st.columns(2)
        old_ticker = col_old.text_input("Old Ticker", placeholder="JEPO").strip().upper()
        new_ticker = col_new.text_input("New Ticker", placeholder="JEPQ").strip().upper()
        
        if st.button("Merge Now", use_container_width=True):
            if not old_ticker or not new_ticker:
                st.error("Both symbols required.")
            else:
                from core.db import get_connection
                conn = get_connection()
                cur = conn.cursor()
                
                # 1. Ensure target asset exists
                upsert_asset_if_missing(new_ticker)
                cur.execute("SELECT id FROM assets WHERE ticker = ?", (new_ticker,))
                new_id = cur.fetchone()[0]
                
                # 2. Update transactions
                cur.execute("SELECT id FROM assets WHERE ticker = ?", (old_ticker,))
                old_row = cur.fetchone()
                if old_row:
                    old_id = old_row[0]
                    cur.execute("UPDATE transactions SET asset_id = ? WHERE asset_id = ?", (new_id, old_id))
                    count_tx = cur.rowcount
                    conn.commit()
                    
                    # 3. Clean up
                    rebuild_holdings_from_transactions()
                    st.success(f"Successfully moved {count_tx} transactions to {new_ticker}!")
                else:
                    st.error(f"Ticker {old_ticker} not found in database.")
                conn.close()
        
    st.markdown("### Research")
    res_ticker = st.text_input("Lookup Ticker")
    if res_ticker:
        st.json(get_basic_info(res_ticker))
