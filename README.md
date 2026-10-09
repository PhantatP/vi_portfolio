
# VI Portfolio (Starter)

Minimal scaffold for your self-hosted Value Investing tracker & research tool.

## Quick start

```bash
# 1) Create venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) Initialize the database
python -m core.db_init

# 3) Add an asset and a holding (examples)
python app/cli.py add-asset --ticker CPALL.BK --name "CP All PCL" --country TH --currency THB --type stock --tags "growth,core"
python app/cli.py add-holding --ticker CPALL.BK --broker SCB --quantity 500 --avg_price 60 --currency THB

# 4) Show portfolio (with yfinance prices)
python app/cli.py portfolio

# 5) Run the minimal web app
streamlit run app/web_app.py
```

## Dime import (no screenshots)

Imports Dime! offshore (US stock) confirmation notes and monthly statements from Gmail.

One-time setup:

1. Put the Dime PDF password in `.env`: `VI_DIME_PDF_PASSWORD=...`
2. In Google Cloud console: create a project, enable the Gmail API, set the OAuth consent
   screen to **In production** (otherwise the token expires every 7 days), create an OAuth
   client of type **Desktop app** and save it as `secrets/gmail_credentials.json`.
3. On a machine with a browser: `python app/cli.py dime-auth` (writes `secrets/gmail_token.json`).
   Copy `secrets/` and `.env` to the Jetson.

Use:

```bash
python app/cli.py dime-sync --dry-run    # show what would be imported/corrected
python app/cli.py dime-sync              # import new PDFs from Gmail
python app/cli.py dime-sync file1.pdf    # or import local PDFs
python app/cli.py dime-reconcile         # DB share counts vs the latest Dime statement
```

API: `POST /api/import/dime/sync?dry_run=true`, `GET /api/import/dime/reconcile`.
`dime-sync` exits with code 1 if any file failed to import.
Re-running is safe: orders are de-duplicated by Dime's order id, and rows typed in earlier
from screenshots are matched and corrected instead of duplicated. Dividends are not in these
PDFs, so they still need to be entered separately.

## Run as Linux services (Jetson)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd frontend && npm install)
bash scripts/install_services.sh                     # daily Dime sync at 09:00
bash scripts/install_services.sh --sync-time 07:30   # or pick a time (system timezone)
bash scripts/install_services.sh --uninstall
```

Run it as your normal user (it calls `sudo` itself). Needs Node.js 20+. It installs and (re)starts
`vi-portfolio-api` (:8000), `vi-portfolio-ui` (:5173) and `vi-portfolio-dime-sync.timer`;
re-run it after `git pull` so the services pick up the new code. Don't run `run_local.sh` at the same time.
On a fresh device, copy `db/vi_portfolio.db`, `.env` and `secrets/` over first (or run `python -m core.db_init`).

Missed syncs (device off) run at next boot. Check results with
`journalctl -u vi-portfolio-dime-sync -n 100`; sync now with `sudo systemctl start vi-portfolio-dime-sync`.
A PDF that fails to import is retried every day and marks the sync unit as failed (`systemctl --failed`).

## Backup

Edit and run `scripts/backup_db.sh`, then set a cron job to copy the DB file to OneDrive regularly.

## Next steps

- Add research functions (business model, notes)
- Add FX conversion
- Add scoring (Quality / Valuation / Country)
- Build richer Streamlit pages
