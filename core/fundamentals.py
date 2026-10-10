"""
Stored financial statements and profiles. A weekly job (`cli.py fundamentals-refresh`) pulls them from
yfinance for every tracked ticker (core/prices.py). Statements are fetched for equities only.
"""
import json
import time

import yfinance as yf

from .db import get_connection
from .prices import SOURCE, tracked_tickers

STATEMENTS = {"income": "get_income_stmt", "balance": "get_balance_sheet", "cashflow": "get_cashflow"}
FREQS = {"annual": "yearly", "quarterly": "quarterly"}
NO_STATEMENTS = {"ETF", "INDEX", "CURRENCY", "CRYPTOCURRENCY", "MUTUALFUND"}
PAUSE_SECONDS = 1.0  # between tickers, to stay clear of Yahoo's rate limit


PROFILE_FIELDS = {  # profiles column -> Yahoo info key
    "quote_type": "quoteType", "name": "longName", "sector": "sector", "industry": "industry",
    "country": "country", "currency": "currency", "financial_currency": "financialCurrency",
    "summary": "longBusinessSummary",
}


def _store_profile(conn, ticker: str, info: dict):
    """Upsert; a field missing from a degraded response keeps its stored value."""
    values = {col: info.get(key) for col, key in PROFILE_FIELDS.items()}
    values["name"] = values["name"] or info.get("shortName")
    cols = list(values)
    conn.execute(
        f"INSERT INTO profiles (ticker, {', '.join(cols)}, source) VALUES (?, {', '.join('?' * len(cols))}, ?) "
        f"ON CONFLICT(ticker) DO UPDATE SET "
        + ", ".join(f"{c} = COALESCE(excluded.{c}, {c})" for c in cols)
        + ", source = excluded.source, fetched_at = CURRENT_TIMESTAMP",
        (ticker, *values.values(), SOURCE))


def _fetch_statements(ticker: str, yt) -> list[tuple]:
    rows = []
    for statement, method in STATEMENTS.items():
        for period_type, freq in FREQS.items():
            df = getattr(yt, method)(pretty=False, freq=freq)  # rows = metrics, columns = period ends
            if df is None or df.empty:
                continue
            for period_end, col in df.items():
                rows += [(ticker, statement, period_type, period_end.strftime("%Y-%m-%d"), metric, float(v), SOURCE)
                         for metric, v in col.dropna().items()]
    return rows


def _store_statements(conn, rows: list[tuple]):
    # Restated figures overwrite. Periods Yahoo no longer serves, and metrics it stops reporting for a
    # period, keep their stored values.
    conn.executemany(
        "INSERT OR REPLACE INTO financials (ticker, statement, period_type, period_end, metric, value, source) "
        "VALUES (?,?,?,?,?,?,?)", rows)


def refresh_fundamentals() -> dict:
    """Profile for every tracked ticker; statements for equities. One ticker failing doesn't stop the rest."""
    tickers = tracked_tickers()
    conn = get_connection()
    run_id = conn.execute("INSERT INTO job_runs (job, status) VALUES ('fundamentals_refresh', 'running')").lastrowid
    conn.commit()
    try:
        profiles, rows, errors = [], {}, {}
        for i, t in enumerate(tickers):
            if i:
                time.sleep(PAUSE_SECONDS)
            try:
                # all network calls first: the write lock is held only for the short write below
                yt = yf.Ticker(t)
                info = yt.info or {}
                statements = _fetch_statements(t, yt) if info.get("quoteType") not in NO_STATEMENTS else None
                if info.get("quoteType"):  # unknown symbols come back as a near-empty dict
                    _store_profile(conn, t, info)
                    profiles.append(t)
                if statements is not None:
                    _store_statements(conn, statements)
                    rows[t] = len(statements)
                conn.commit()
            except Exception as e:
                conn.rollback()
                errors[t] = repr(e)

        summary = {
            "tickers": len(tickers),
            "profiles": len(profiles),
            "rows": sum(rows.values()),
            "no_statements": [t for t, n in rows.items() if n == 0],
            "errors": errors,
        }
        got_statements = any(rows.values())
        if (not profiles and not got_statements) or (rows and not got_statements):
            status = "error"    # nothing came back, or every equity came back empty (e.g. rate limited)
        elif errors:
            status = "partial"  # the CLI exits non-zero, so systemd shows the failed tickers
        else:
            status = "ok"
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
