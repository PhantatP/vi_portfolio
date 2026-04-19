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

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized.")
