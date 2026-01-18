
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

## Backup

Edit and run `scripts/backup_db.sh`, then set a cron job to copy the DB file to OneDrive regularly.

## Next steps

- Add research functions (business model, notes)
- Add FX conversion
- Add scoring (Quality / Valuation / Country)
- Build richer Streamlit pages
