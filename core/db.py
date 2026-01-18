import os
import sqlite3
from pathlib import Path

# Path to the SQLite DB file (defaults to ./db/vi_portfolio.db)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "vi_portfolio.db"
DB_PATH = Path(os.getenv("VI_DB_PATH", DEFAULT_DB_PATH))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
