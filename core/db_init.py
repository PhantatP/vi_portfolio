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

BENCHMARKS = ("^SET.BK", "^GSPC", "^IXIC")  # SET, S&P 500, NASDAQ Composite

MARKET_DATA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,        -- Yahoo symbol, upper case
    reason TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- One row per ticker per trading day. close is Yahoo's Close: split-adjusted, NOT dividend-adjusted.
-- Today's row is overwritten by each refresh until the day is over.
CREATE TABLE IF NOT EXISTS price_daily (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,             -- YYYY-MM-DD, exchange-local trading date
    close REAL NOT NULL,
    volume REAL,
    source TEXT NOT NULL,           -- yfinance
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS corporate_actions (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,             -- ex-date, YYYY-MM-DD
    type TEXT NOT NULL,             -- dividend (cash per share) / split (ratio, e.g. 4.0 for 4:1)
    value REAL NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date, type)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL,              -- e.g. prices_refresh
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL,           -- running / ok / error
    detail TEXT                     -- JSON summary or error message
);
"""

def _m1_baseline(cur):
    """Schema from before numbered migrations; also brings old, unversioned DBs up to it."""
    cur.executescript(SCHEMA_SQL)
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

def _m2_market_data(cur):
    """Stored prices for held + watched tickers (core/prices.py)."""
    cur.executescript(MARKET_DATA_SQL)
    cur.executemany("INSERT OR IGNORE INTO watchlist (ticker, reason) VALUES (?, 'benchmark');",
                    [(t,) for t in BENCHMARKS])

FUNDAMENTALS_SQL = """
-- Yahoo only serves the last ~4 years / ~5 quarters, so rows are kept after they drop off upstream.
CREATE TABLE IF NOT EXISTS financials (
    ticker TEXT NOT NULL,
    statement TEXT NOT NULL,        -- income / balance / cashflow
    period_type TEXT NOT NULL,      -- annual / quarterly
    period_end TEXT NOT NULL,       -- YYYY-MM-DD
    metric TEXT NOT NULL,           -- Yahoo's raw key, e.g. TotalRevenue, StockholdersEquity
    value REAL NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, statement, period_type, period_end, metric)
) WITHOUT ROWID;

-- Latest descriptive data per tracked ticker. Separate from assets, which is the transaction ledger.
CREATE TABLE IF NOT EXISTS profiles (
    ticker TEXT PRIMARY KEY,
    quote_type TEXT,                -- EQUITY / ETF / INDEX / CURRENCY / ...
    name TEXT,
    sector TEXT,
    industry TEXT,
    country TEXT,
    currency TEXT,                  -- trading currency: price_daily is in this
    financial_currency TEXT,        -- reporting currency: financials are in this (TM: JPY, trades in USD)
    summary TEXT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def _m3_fundamentals(cur):
    """Stored financial statements and profiles (core/fundamentals.py)."""
    cur.executescript(FUNDAMENTALS_SQL)

# Append-only: never edit or reorder a step that has shipped. PRAGMA user_version = steps applied.
# Steps must be idempotent, since a crash between a step and its version bump re-runs it.
MIGRATIONS = [_m1_baseline, _m2_market_data, _m3_fundamentals]

_schema_ready = False

def init_db():
    """Apply pending migrations. Cheap after the first call in a process."""
    global _schema_ready
    if _schema_ready:
        return
    conn = get_connection()
    conn.execute("PRAGMA journal_mode=WAL;")  # persistent: readers don't block the price refresh writer
    version = conn.execute("PRAGMA user_version;").fetchone()[0]
    for n, step in enumerate(MIGRATIONS[version:], start=version + 1):
        step(conn.cursor())
        conn.execute(f"PRAGMA user_version = {n};")
        conn.commit()
    conn.close()
    _schema_ready = True

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized.")
