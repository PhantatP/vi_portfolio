# Data design: stored market data for the UI and AI agents

Goal: VI Portfolio becomes a stock data service that AI agents query (read-only, over MCP), running on
the Jetson and called from the laptop. yfinance is slow and unreliable, and its raw payloads cost agents
many tokens, so data is fetched on a schedule, stored in SQLite, and served from the DB.

## Decisions

- **SQLite stays.** One machine, one writer (the refresh jobs), a few readers. Expected size is under
  ~150 MB after decades of daily data. WAL mode keeps readers from blocking the writer. Keep the live DB
  on local disk, not in a synced folder (OneDrive etc.), because sync tools can corrupt WAL files.
- **Agents are read-only.** The MCP server gets no write tools.
- **Facts vs derived.** Prices, financial statements and corporate actions are facts: upserted, never
  thrown away. Ratios, valuations and briefs are derived: recomputable, stored with `computed_at`.
- **Every fact row records `source`** so another provider can be added if yfinance breaks.
- **Tracked tickers** = held (`holdings.quantity > 0`) + `watchlist` + `USDTHB=X`. A ticker that drops
  out keeps its history and just stops refreshing. Benchmarks are ordinary watchlist entries.

## Schema changes

Numbered migrations in `core/db_init.py`. `PRAGMA user_version` = number of steps applied. `init_db()`
runs pending steps and is called lazily by the code that needs the schema. Rules: append only, never
edit a shipped step, and make every step idempotent.

## Phases

### 1. Prices (done)

- `watchlist(ticker, reason, added_at)`, seeded with `^SET.BK`, `^GSPC`, `^IXIC`.
- `price_daily(ticker, date, close, volume, source, fetched_at)`, keyed on (ticker, date).
- `corporate_actions(ticker, date, type, value, source, fetched_at)`: `dividend` (cash/share) and
  `split` (ratio).
- `job_runs(job, started_at, finished_at, status, detail)`.
- `cli.py prices-refresh` runs hourly from the `vi-portfolio-prices` systemd timer. New tickers get
  their full history (`period="max"`). Existing ones are re-fetched from their last stored date minus
  7 days, grouped by that date (so one frozen ticker doesn't widen everyone's window), so Yahoo's late
  corrections overwrite stored rows.
- Downloads go in batches of 10 tickers. A batch's frame spans the union of all its tickers' dates
  (back to 1927 for `^GSPC`), so batching caps memory: measured peak for a 51-ticker backfill went
  from 303 MB to 196 MB. The job runs as a oneshot process, so nothing accumulates between runs.
- `portfolio.fetch_latest_prices()` reads the DB and returns `as_of`. Live yfinance is used only for
  tickers with no stored rows yet. `fx.fetch_usd_thb_rate()` uses the stored rate if it is at most
  7 days old, then tries live, then falls back to the stale stored rate before the hard-coded default.

**Price basis.** `close` is Yahoo's `Close`: split-adjusted, **not** dividend-adjusted. After a split,
Yahoo re-bases the ticker's whole history, sometimes days late. Each refresh compares the fetched
closes with the stored ones on finalized days in the overlap window. The last stored day is skipped,
since it may be an intraday snapshot. A move of more than 1% means the history was re-based, so the
ticker is re-fetched in full and every stored row stays on one basis. If that re-fetch fails, nothing
is stored for the ticker and it's retried next run. Total return can be computed later from
`corporate_actions`.

**Memory in the API process.** `research.py`'s `ttl_cache` used to keep every entry forever (one
per ticker ever researched, including price-history frames). It now drops expired entries and holds
at most 256 per function, so the worst case is a few MB. It is still per-process and lost on restart;
the persistent DB-backed cache comes with phases 2–3. Still open: the easyocr reader (with torch)
stays loaded for the life of the process after the first OCR scan.

**Known gap.** Yahoo serves no history for Thai indices (`^SET.BK` returns only today, and `^SET50.BK`
only allows 1d/5d). Their history builds up from the first refresh onward. `TDEX.BK` (SET50 ETF,
history since 2008) can serve as a backfillable proxy if needed.

### 2. Financials

`financials(ticker, period_type, period_end, metric, value, source, fetched_at)` in long format,
because line items differ by industry (banks, REITs, tech). Refreshed weekly. Skips `index`/FX tickers.
Profile fields (name, sector, summary) are refreshed weekly into `assets`.

### 3. Ticker briefs

`ticker_brief(ticker, brief_json, computed_at, data_as_of)`: a compact (~300–500 token) summary of
valuation, quality, trend and position, rebuilt after each refresh. Agents read this first.

### 4. MCP server

Mounted inside the FastAPI app at `/mcp` (one service, one port, one cache). Read-only tools: briefs,
portfolio vs target, watchlist, price history queries (downsampled), notes. Laptop connects with
`claude mcp add --transport http vi-portfolio http://<jetson>:8000/mcp`.

## Size estimate

About 100 tickers over 30 years: ~750k price rows (~50 MB) plus ~600k financial rows (~40 MB). The
first real backfill (7 holdings, 3 indices, FX; full history) was 91k rows and 6.6 MB.
