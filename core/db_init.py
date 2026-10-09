from .db import get_connection

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    name TEXT,
    country TEXT,
    currency TEXT,
    type TEXT,           -- stock, etf, fund, crypto
    sector TEXT,
    industry TEXT,
    tags TEXT,           -- comma-separated: growth,dividend,core
    target_weight REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    broker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_price REAL NOT NULL,
    currency TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    broker TEXT NOT NULL,
    trade_date TEXT NOT NULL,       -- YYYY-MM-DD
    side TEXT NOT NULL,             -- buy / sell
    quantity REAL NOT NULL,
    price REAL,                     -- per-share price
    fee REAL DEFAULT 0,
    currency TEXT,                  -- legacy mirror
    price_ccy TEXT,
    thb_amount REAL,
    usd_amount REAL,
    fx_thb_per_usd REAL,
    fee_ccy TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL UNIQUE,
    my_summary TEXT,
    business_model TEXT,
    revenue_model TEXT,
    future_view TEXT,
    risk_view TEXT,
    rating TEXT,                    -- watch, buy_on_dip, buy, avoid
    growth_dividend TEXT,           -- growth, dividend, mixed
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
"""

_import_schema_ready = False

def ensure_import_schema():
    """Idempotent: columns/tables used by broker document imports (core/dime_import.py)."""
    global _import_schema_ready
    if _import_schema_ready:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(transactions);")
    if not any(r[1] == "external_id" for r in cur.fetchall()):
        cur.execute("ALTER TABLE transactions ADD COLUMN external_id TEXT;")  # broker's own order id
    cur.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_broker_external_id
            ON transactions(broker, external_id) WHERE external_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS imported_files (
            file_key TEXT PRIMARY KEY,      -- broker file name, e.g. Dime_offshore_confirmationNote_DIMEOS....pdf
            kind TEXT NOT NULL,             -- confirmation_note / monthly_statement
            status TEXT NOT NULL,           -- ok / error
            detail TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    _import_schema_ready = True

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    ensure_import_schema()

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized.")
