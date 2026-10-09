"""
Stored daily prices. A scheduled job (`cli.py prices-refresh`) pulls from yfinance into price_daily;
readers use the DB so the UI and agents never wait on Yahoo.

Tracked tickers = held (quantity > 0) + watchlist + USD/THB. A ticker that drops out keeps its
history; it just stops being refreshed.
"""
import json
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from .db import get_connection
from .db_init import init_db

USD_THB = "USDTHB=X"
SOURCE = "yfinance"
OVERLAP_DAYS = 7  # re-fetch recent days so late corrections from Yahoo overwrite stored rows
BATCH = 10  # tickers per yfinance call; a call's frame spans the union of all their dates, so this caps memory
COLUMNS = ["Close", "Volume", "Dividends", "Stock Splits"]
REBASE_TOLERANCE = 0.01  # a finalized close that moved more than this means Yahoo re-based the history


def tracked_tickers() -> list[str]:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.ticker FROM holdings h JOIN assets a ON a.id = h.asset_id WHERE h.quantity > 0
        UNION SELECT ticker FROM watchlist
    """).fetchall()
    conn.close()
    return sorted({r[0].upper() for r in rows} | {USD_THB})


def _download(tickers: list[str], **kwargs) -> dict[str, pd.DataFrame]:
    """Batched yfinance calls. Returns {ticker: frame} for tickers that came back with prices."""
    out = {}
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i + BATCH]
        df = yf.download(chunk, auto_adjust=False, actions=True, group_by="ticker",
                         progress=False, threads=True, **kwargs)
        if len(chunk) == 1 and not df.empty and not isinstance(df.columns, pd.MultiIndex):
            df = pd.concat({chunk[0]: df}, axis=1)  # older yfinance returns flat columns for one ticker
        for t in chunk:
            if t not in df.columns.get_level_values(0):
                continue
            f = df[t]
            # mixed markets: a US ticker has NaN rows on Thai-only trading days
            f = f[[c for c in COLUMNS if c in f]].dropna(subset=["Close"])
            if not f.empty:
                out[t] = f
    return out


def _history_rebased(conn, ticker: str, f: pd.DataFrame, last_date: str) -> bool:
    """
    After a split Yahoo re-bases all past closes, sometimes days late. A finalized close that no longer
    matches the stored one means stored history is on a stale basis. The last stored day is skipped:
    it may be an intraday snapshot.
    """
    dates = f.index.strftime("%Y-%m-%d")
    stored = dict(conn.execute("SELECT date, close FROM price_daily WHERE ticker = ? AND date >= ? AND date < ?",
                               (ticker, dates[0], last_date)).fetchall())
    return any(d in stored and abs(c / stored[d] - 1) > REBASE_TOLERANCE for d, c in zip(dates, f["Close"]))


def _store(conn, ticker: str, f: pd.DataFrame) -> int:
    dates = f.index.strftime("%Y-%m-%d")
    volume = f["Volume"] if "Volume" in f else pd.Series(index=f.index, dtype=float)
    conn.executemany(
        "INSERT OR REPLACE INTO price_daily (ticker, date, close, volume, source) VALUES (?,?,?,?,?)",
        [(ticker, d, float(c), None if pd.isna(v) else float(v), SOURCE)
         for d, c, v in zip(dates, f["Close"], volume)])
    for col, kind in (("Dividends", "dividend"), ("Stock Splits", "split")):
        if col not in f:
            continue
        s = f[col].fillna(0)
        s = s[s != 0]
        conn.executemany(
            "INSERT OR REPLACE INTO corporate_actions (ticker, date, type, value, source) VALUES (?,?,?,?,?)",
            [(ticker, d, kind, float(v), SOURCE) for d, v in zip(s.index.strftime("%Y-%m-%d"), s)])
    return len(dates)


def refresh_prices() -> dict:
    """Backfill new tickers (full history), update the rest from their last stored date."""
    tickers = tracked_tickers()
    conn = get_connection()
    run_id = conn.execute("INSERT INTO job_runs (job, status) VALUES ('prices_refresh', 'running')").lastrowid
    conn.commit()
    try:
        last = dict(conn.execute("SELECT ticker, MAX(date) FROM price_daily GROUP BY ticker").fetchall())
        new = [t for t in tickers if t not in last]

        # grouped by last stored date, so one ticker that stopped updating doesn't widen every download
        by_last = {}
        for t in tickers:
            if t in last:
                by_last.setdefault(last[t], []).append(t)
        frames = {}
        for last_date, group in by_last.items():
            start = date.fromisoformat(last_date) - timedelta(days=OVERLAP_DAYS)
            frames.update(_download(group, start=start.isoformat()))
        # re-fetch re-based tickers in full so all stored rows share one basis
        rebased = [t for t, f in frames.items() if _history_rebased(conn, t, f, last[t])]
        if new or rebased:
            full = _download(new + rebased, period="max")
            for t in rebased:
                if t not in full:
                    del frames[t]  # don't store a new-basis tail on top of old-basis history; retry next run
            frames.update(full)

        rows = {t: _store(conn, t, f) for t, f in frames.items()}
        summary = {
            "tickers": len(tickers),
            "rows": sum(rows.values()),
            "backfilled": [t for t in new if t in frames],
            "rebased": [t for t in rebased if t in frames],
            "missing": [t for t in tickers if t not in frames],
        }
        status = "ok" if frames else "error"
        conn.execute("UPDATE job_runs SET status = ?, finished_at = CURRENT_TIMESTAMP, detail = ? WHERE id = ?",
                     (status, json.dumps(summary), run_id))
        conn.commit()
        return {"status": status, **summary}
    except Exception as e:
        conn.rollback()
        conn.execute("UPDATE job_runs SET status = 'error', finished_at = CURRENT_TIMESTAMP, detail = ? WHERE id = ?",
                     (repr(e), run_id))
        conn.commit()
        raise
    finally:
        conn.close()


def latest_prices(tickers: list[str]) -> pd.DataFrame:
    """Latest stored close per ticker: columns ticker, price, as_of. Tickers with no rows are absent."""
    init_db()
    tickers = [t.upper() for t in tickers if t]
    if not tickers:
        return pd.DataFrame(columns=["ticker", "price", "as_of"])
    conn = get_connection()
    # SQLite takes the bare `close` column from the row holding MAX(date).
    df = pd.read_sql_query(
        f"SELECT ticker, close AS price, MAX(date) AS as_of FROM price_daily "
        f"WHERE ticker IN ({','.join('?' * len(tickers))}) GROUP BY ticker",
        conn, params=tickers)
    conn.close()
    return df


def add_to_watchlist(ticker: str, reason: str | None = None) -> str:
    init_db()
    t = ticker.strip().upper()
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO watchlist (ticker, reason) VALUES (?, ?)", (t, reason))
    conn.commit()
    conn.close()
    return t


def remove_from_watchlist(ticker: str) -> bool:
    """Stops refreshing the ticker unless it's held; stored history is kept."""
    init_db()
    conn = get_connection()
    removed = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.strip().upper(),)).rowcount
    conn.commit()
    conn.close()
    return removed > 0


def list_watchlist() -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT w.ticker, w.reason, w.added_at, MAX(p.date)
        FROM watchlist w LEFT JOIN price_daily p ON p.ticker = w.ticker
        GROUP BY w.ticker ORDER BY w.ticker
    """).fetchall()
    conn.close()
    return [{"ticker": t, "reason": r, "added_at": a, "last_price_date": d} for t, r, a, d in rows]
