# core/dime_import.py
"""
Import Dime! offshore PDFs into the DB, from Gmail or from files on disk.

Safe to re-run:
  - files already imported OK are skipped (imported_files table)
  - orders already in the DB are skipped by external_id ("<note no>:<order id>")
  - rows typed in earlier from screenshots (no external_id) are matched by
    ticker/side/quantity/date and corrected with the PDF values instead of duplicated
Monthly statements are not imported as transactions; they are kept as a snapshot
and used to reconcile the DB holdings against what Dime reports.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from .db import get_connection, PROJECT_ROOT
from .db_init import ensure_import_schema
from .dime_pdf import read_pdf_text, parse_confirmation_note, parse_monthly_statement, DimeParseError
from .transactions import add_transaction, rebuild_holdings_from_transactions

load_dotenv(PROJECT_ROOT / ".env")

BROKER = "Dime"
KINDS = {
    "Dime_offshore_confirmationNote": "confirmation_note",
    "Dime_monthly_statement": "monthly_statement",
}
QTY_TOLERANCE = 1e-5      # screenshot OCR sometimes drops the 7th decimal
DATE_WINDOW_DAYS = 4      # screenshot dates may be settlement rather than trade date


def file_kind(filename: str) -> str | None:
    if not filename.lower().endswith(".pdf"):
        return None
    return next((kind for prefix, kind in KINDS.items() if filename.startswith(prefix)), None)


def imported_ok_files() -> set[str]:
    ensure_import_schema()
    conn = get_connection()
    rows = conn.execute("SELECT file_key FROM imported_files WHERE status = 'ok'").fetchall()
    conn.close()
    return {r[0] for r in rows}


def _record_file(filename, kind, status, detail):
    conn = get_connection()
    conn.execute(
        """INSERT INTO imported_files (file_key, kind, status, detail) VALUES (?, ?, ?, ?)
           ON CONFLICT(file_key) DO UPDATE SET status=excluded.status, detail=excluded.detail,
                                                imported_at=CURRENT_TIMESTAMP""",
        (filename, kind, status, detail),
    )
    conn.commit()
    conn.close()


def _find_legacy_row(cur, row, claimed: set[int]):
    d = date.fromisoformat(row["trade_date"])
    cur.execute(
        """SELECT t.id, t.trade_date, t.quantity, t.price FROM transactions t
           JOIN assets a ON a.id = t.asset_id
           WHERE t.broker = ? AND a.ticker = ? AND t.side = ? AND t.external_id IS NULL
             AND t.trade_date BETWEEN ? AND ? AND ABS(t.quantity - ?) <= ?
           ORDER BY ABS(julianday(t.trade_date) - julianday(?))""",
        (BROKER, row["ticker"], row["side"],
         str(d - timedelta(days=DATE_WINDOW_DAYS)), str(d + timedelta(days=DATE_WINDOW_DAYS)),
         row["quantity"], QTY_TOLERANCE, row["trade_date"]),
    )
    match = next((r for r in cur.fetchall() if r[0] not in claimed), None)
    if match or row["quantity"] == int(row["quantity"]):
        return match
    # Screenshot rows sometimes got a wrong date; an identical fractional qty (7 dp) at the
    # identical price is the same trade whatever the date
    cur.execute(
        """SELECT t.id, t.trade_date, t.quantity, t.price FROM transactions t
           JOIN assets a ON a.id = t.asset_id
           WHERE t.broker = ? AND a.ticker = ? AND t.side = ? AND t.external_id IS NULL
             AND ABS(t.quantity - ?) < 5e-8 AND ABS(t.price - ?) < 0.005
           ORDER BY ABS(julianday(t.trade_date) - julianday(?))""",
        (BROKER, row["ticker"], row["side"], row["quantity"], row["price"], row["trade_date"]),
    )
    return next((r for r in cur.fetchall() if r[0] not in claimed), None)


def import_confirmation_note(parsed: dict, dry_run: bool, claimed: set[int]) -> dict:
    result = {"inserted": [], "corrected": [], "existing": [],
              "skipped": parsed["skipped"], "errors": list(parsed["errors"])}
    conn = get_connection()
    try:
        _import_rows(conn, parsed["rows"], dry_run, claimed, result)
    finally:
        conn.close()
    return result


def _import_rows(conn, rows, dry_run, claimed, result):
    cur = conn.cursor()
    for row in rows:
        label = f"{row['trade_date']} {row['side']} {row['quantity']} {row['ticker']} @ {row['price']}"
        cur.execute("SELECT 1 FROM transactions WHERE broker = ? AND external_id = ?", (BROKER, row["external_id"]))
        if cur.fetchone():
            result["existing"].append(label)
            continue

        legacy = _find_legacy_row(cur, row, claimed)
        if legacy:
            tx_id, old_date, old_qty, old_price = legacy
            claimed.add(tx_id)
            result["corrected"].append(f"{label} (was #{tx_id}: {old_date} qty {old_qty} @ {old_price})")
            if not dry_run:
                cur.execute(
                    """UPDATE transactions SET trade_date=?, quantity=?, price=?, fee=?, fee_ccy=?, currency=?,
                              price_ccy=?, thb_amount=?, usd_amount=?, fx_thb_per_usd=?, external_id=?
                       WHERE id=?""",
                    (row["trade_date"], row["quantity"], row["price"], row["fee"], row["price_ccy"],
                     row["price_ccy"], row["price_ccy"], row["thb_amount"], row["usd_amount"],
                     row["fx_thb_per_usd"], row["external_id"], tx_id),
                )
                conn.commit()  # release the write lock before add_transaction opens its own connection
            continue

        result["inserted"].append(label)
        if not dry_run:
            add_transaction(
                ticker=row["ticker"], broker=BROKER, trade_date=row["trade_date"], side=row["side"],
                quantity=row["quantity"], price_per_share=row["price"], price_ccy=row["price_ccy"],
                fee=row["fee"], fee_ccy=row["price_ccy"], thb_amount=row["thb_amount"],
                usd_amount=row["usd_amount"], fx_thb_per_usd=row["fx_thb_per_usd"],
                external_id=row["external_id"],
            )


def reconcile(statement: dict) -> dict:
    """
    Compare Dime's month-end share counts with the DB (Dime USD trades up to the statement date).
    The statement excludes unsettled trades, so a trade on the month's last trading day shows as a mismatch.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.ticker,
                  SUM(CASE t.side WHEN 'buy' THEN t.quantity WHEN 'sell' THEN -t.quantity ELSE 0 END)
           FROM transactions t JOIN assets a ON a.id = t.asset_id
           WHERE t.broker = ? AND t.price_ccy = 'USD' AND t.trade_date <= ?
           GROUP BY a.ticker""",
        (BROKER, statement["as_of"]),
    ).fetchall()
    conn.close()
    db = {ticker: qty or 0.0 for ticker, qty in rows}
    dime = {h["ticker"]: h["shares"] for h in statement["holdings"]}

    mismatches = []
    for ticker in sorted(set(db) | set(dime)):
        diff = dime.get(ticker, 0.0) - db.get(ticker, 0.0)
        if abs(diff) > QTY_TOLERANCE:
            mismatches.append({"ticker": ticker, "dime_shares": dime.get(ticker, 0.0),
                               "db_shares": round(db.get(ticker, 0.0), 7), "diff": round(diff, 7)})
    return {"as_of": statement["as_of"], "matches": not mismatches, "mismatches": mismatches,
            "cash_usd": statement["cash_usd"],
            "dividends_since_start_usd": statement["dividends_since_start_usd"]}


def latest_statement() -> dict | None:
    ensure_import_schema()
    conn = get_connection()
    rows = conn.execute(
        "SELECT detail FROM imported_files WHERE kind = 'monthly_statement' AND status = 'ok'"
    ).fetchall()
    conn.close()
    statements = [json.loads(r[0]) for r in rows]
    return max(statements, key=lambda s: s["as_of"], default=None)


def import_files(files: list[tuple[str, bytes]], dry_run: bool = False) -> dict:
    """
    files: (filename, pdf bytes). Notes are imported before statements so the
    reconciliation sees the newest trades.
    """
    ensure_import_schema()
    password = os.getenv("VI_DIME_PDF_PASSWORD")
    if not password:
        raise RuntimeError("Set VI_DIME_PDF_PASSWORD in .env (the password Dime uses for its PDFs)")

    files = sorted((f for f in files if file_kind(f[0])), key=lambda f: (file_kind(f[0]) != "confirmation_note", f[0]))
    claimed: set[int] = set()
    results, statements = [], []
    for filename, data in files:
        kind = file_kind(filename)
        try:
            text = read_pdf_text(data, password)
            if kind == "confirmation_note":
                res = import_confirmation_note(parse_confirmation_note(text), dry_run, claimed)
                status, detail = ("error" if res["errors"] else "ok"), json.dumps(res["errors"])
            else:
                statement = parse_monthly_statement(text)
                statements.append(statement)
                res = {"as_of": statement["as_of"], "holdings": len(statement["holdings"])}
                status, detail = "ok", json.dumps(statement)
        except Exception as e:  # recorded per file; the rest of the batch still imports
            msg = str(e) if isinstance(e, DimeParseError) else f"{type(e).__name__}: {e}"
            res, status, detail = {"errors": [msg]}, "error", json.dumps([msg])
        results.append({"file": filename, "kind": kind, "status": status, **res})
        if not dry_run:
            _record_file(filename, kind, status, detail)

    # Always rebuild after real imports: an earlier run may have written rows and then failed,
    # and a new statement re-anchors avg costs
    if not dry_run and files:
        rebuild_holdings_from_transactions()

    statement = max(statements, key=lambda s: s["as_of"], default=None) or latest_statement()
    return {
        "dry_run": dry_run,
        "files": results,
        "totals": {k: sum(len(r.get(k, [])) for r in results)
                   for k in ("inserted", "corrected", "existing", "skipped", "errors")},
        "reconciliation": reconcile(statement) if statement else None,
        **({"note": "dry run: nothing was written; reconciliation uses the DB as it is now"} if dry_run else {}),
    }


def import_paths(paths: list[str], dry_run: bool = False) -> dict:
    return import_files([(Path(p).name, Path(p).read_bytes()) for p in paths], dry_run)


def sync_from_gmail(dry_run: bool = False) -> dict:
    from .gmail_source import fetch_attachments
    skip = imported_ok_files()
    files = fetch_attachments(lambda name: file_kind(name) is not None and name not in skip)
    summary = import_files(files, dry_run)
    summary["already_imported_files"] = len(skip)
    return summary
