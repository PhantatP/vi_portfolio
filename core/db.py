import os
import sqlite3
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Path to the SQLite DB file. Set VI_DB_PATH in .env; it wins over the process environment so a
# stale systemd Environment= line can't point the app at an empty DB.
# Defaults to OneDrive/vi_portfolio/db/vi_portfolio.db under the current user home.
DEFAULT_DB_PATH = Path.home() / "OneDrive" / "vi_portfolio" / "db" / "vi_portfolio.db"
DB_PATH = Path(os.path.expanduser(
    dotenv_values(PROJECT_ROOT / ".env").get("VI_DB_PATH") or os.getenv("VI_DB_PATH") or DEFAULT_DB_PATH
))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)  # wait out another process's write (e.g. price refresh)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
