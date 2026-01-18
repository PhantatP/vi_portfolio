# scripts/migrate_001_add_fx_columns.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.db import get_connection

def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def add_column_if_missing(cur, table, col, decl):
    if not column_exists(cur, table, col):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl};")

def run():
    conn = get_connection()
    cur = conn.cursor()

    # New columns on transactions:
    # - price_ccy: currency of per-share price (default USD)
    # - thb_amount: total THB actually paid (gross or net; see fee)
    # - usd_amount: total USD notionals (qty*price if you want to store it)
    # - fx_thb_per_usd: explicit FX for the transaction (optional)
    # - fee_ccy: currency of fee (USD/THB)
    add_column_if_missing(cur, "transactions", "price_ccy", "TEXT")
    add_column_if_missing(cur, "transactions", "thb_amount", "REAL")
    add_column_if_missing(cur, "transactions", "usd_amount", "REAL")
    add_column_if_missing(cur, "transactions", "fx_thb_per_usd", "REAL")
    add_column_if_missing(cur, "transactions", "fee_ccy", "TEXT")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    run()
    print("✅ Migration applied: added FX/THB columns to transactions.")
