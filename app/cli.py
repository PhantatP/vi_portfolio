
import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is in the path when run as `python app/cli.py`
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.db_init import init_db
from core.db import get_connection

def add_asset(args):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO assets (ticker, name, country, currency, type, sector, industry, tags) VALUES (?,?,?,?,?,?,?,?)",
        (args.ticker, args.name, args.country, args.currency, args.type, args.sector, args.industry, args.tags)
    )
    conn.commit()
    conn.close()
    print(f"✅ asset upserted: {args.ticker}")

def add_holding(args):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM assets WHERE ticker = ?", (args.ticker,))
    row = cur.fetchone()
    if not row:
        raise SystemExit("Asset not found. Add the asset first with `cli.py add-asset`.")
    asset_id = row[0]
    cur.execute(
        "INSERT INTO holdings (asset_id, broker, quantity, avg_price, currency) VALUES (?,?,?,?,?)",
        (asset_id, args.broker, args.quantity, args.avg_price, args.currency)
    )
    conn.commit()
    conn.close()
    print(f"✅ holding added for {args.ticker} @ broker {args.broker}")

def portfolio(args):
    from core.portfolio import build_portfolio_view  # pre-existing: no longer exists in core.portfolio
    df, total = build_portfolio_view()
    if df.empty:
        print("No holdings yet. Add some with `cli.py add-asset` and `cli.py add-holding`.")
        return
    print(df[["ticker","broker","quantity","price","value","weight"]].to_string(index=False))
    print(f"—— Total portfolio value (mixed currencies): {total:,.2f}")

def init(args):
    init_db()

def dime_auth(args):
    from core.gmail_source import authorize
    print(f"Gmail token saved to {authorize()}")

def dime_sync(args):
    from core.dime_import import sync_from_gmail, import_paths
    summary = import_paths(args.files, args.dry_run) if args.files else sync_from_gmail(args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

def dime_reconcile(args):
    from core.dime_import import latest_statement, reconcile
    statement = latest_statement()
    if statement is None:
        raise SystemExit("No Dime monthly statement imported yet.")
    print(json.dumps(reconcile(statement), indent=2, ensure_ascii=False))

def main():
    p = argparse.ArgumentParser(prog="cli.py", description="VI Portfolio CLI")
    sub = p.add_subparsers()

    sp = sub.add_parser("init-db", help="Create tables if they don't exist")
    sp.set_defaults(func=init)

    sp = sub.add_parser("add-asset", help="Add or update an asset master record")
    sp.add_argument("--ticker", required=True)
    sp.add_argument("--name", default=None)
    sp.add_argument("--country", default=None)
    sp.add_argument("--currency", default=None)
    sp.add_argument("--type", default="stock")
    sp.add_argument("--sector", default=None)
    sp.add_argument("--industry", default=None)
    sp.add_argument("--tags", default=None)
    sp.set_defaults(func=add_asset)

    sp = sub.add_parser("add-holding", help="Add a holding row for an existing asset")
    sp.add_argument("--ticker", required=True)
    sp.add_argument("--broker", required=True)
    sp.add_argument("--quantity", type=float, required=True)
    sp.add_argument("--avg_price", type=float, required=True)
    sp.add_argument("--currency", required=True)
    sp.set_defaults(func=add_holding)

    sp = sub.add_parser("portfolio", help="Show portfolio with latest prices")
    sp.set_defaults(func=portfolio)

    sp = sub.add_parser("dime-auth", help="One-time Gmail sign-in (needs a browser)")
    sp.set_defaults(func=dime_auth)

    sp = sub.add_parser("dime-sync", help="Import Dime PDFs from Gmail, or from the given files")
    sp.add_argument("files", nargs="*", help="Local Dime PDFs; omit to fetch from Gmail")
    sp.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    sp.set_defaults(func=dime_sync)

    sp = sub.add_parser("dime-reconcile", help="Compare DB holdings with the latest Dime statement")
    sp.set_defaults(func=dime_reconcile)

    args = p.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
