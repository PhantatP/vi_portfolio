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
the persistent DB-backed cache comes with phases 2–3. OCR receipt scanning (easyocr + torch) was
removed, since the Dime Gmail import replaces it.

**Known gap.** Yahoo serves no history for Thai indices (`^SET.BK` returns only today, and `^SET50.BK`
only allows 1d/5d). Their history builds up from the first refresh onward. `TDEX.BK` (SET50 ETF,
history since 2008) can serve as a backfillable proxy if needed.

### 2. Financials (done)

- `financials(ticker, statement, period_type, period_end, metric, value, source, fetched_at)` in long
  format, because line items differ by industry (banks, REITs, tech). `statement` is income / balance /
  cashflow, `period_type` is annual / quarterly, and `metric` is Yahoo's raw key (`TotalRevenue`, not
  "Total Revenue"), since raw keys are stable identifiers.
- **Yahoo only serves the last ~4 years and ~5 quarters**, so this table is the only way to build
  longer history: periods that drop off upstream are kept, and so are metrics Yahoo stops reporting
  for a period. Restated figures overwrite stored ones.
- `profiles(ticker, quote_type, name, sector, industry, country, currency, financial_currency, summary,
  source, fetched_at)` for every tracked ticker. This is a separate table, not columns in `assets`:
  `assets` is the transaction ledger, watchlist tickers have no row there, and `/api/assets` would
  start listing them. A degraded Yahoo response doesn't blank stored fields (upsert with `COALESCE`).
- **Two currencies.** `currency` is the trading currency, which `price_daily` uses. `financial_currency`
  is the reporting currency, which `financials` uses. They differ for ADRs and some foreign listings:
  TM trades in USD but reports in JPY. Any ratio mixing price and statements (P/E, P/B, market cap)
  must convert between them first.
- `cli.py fundamentals-refresh` runs weekly from the `vi-portfolio-fundamentals` systemd timer
  (Sunday 06:30, outside both markets' sessions). Statements are fetched only when `quote_type` is not
  ETF / INDEX / CURRENCY / CRYPTOCURRENCY / MUTUALFUND. Tickers are processed one at a time with a 1 s
  pause and their own commit, so one failure doesn't stop the rest. Each ticker's network calls finish
  before its write starts, so the job never holds the DB write lock while waiting on Yahoo.
- Status: `ok`, `partial` (some tickers errored), or `error` (nothing came back, or every equity
  returned no statements, which is what a rate limit swallowed by yfinance looks like). The CLI exits
  non-zero unless `ok`, so systemd shows the failure.
- First real run: 4 equities gave 6,053 rows (~1,500 per stock, ~150 bytes per row) in ~15–20 s.

### 3. Ticker briefs

`ticker_brief(ticker, brief_json, computed_at, data_as_of)`: a compact (~300–500 token) summary of
valuation, quality, trend and position, rebuilt after each refresh. Agents read this first.

### 4. MCP server

Mounted inside the FastAPI app at `/mcp` (one service, one port, one cache). Read-only tools: briefs,
portfolio vs target, watchlist, price history queries (downsampled), notes. Laptop connects with
`claude mcp add --transport http vi-portfolio http://<jetson>:8000/mcp`.

## Size estimate

- **Prices:** about 100 tickers over 30 years is ~750k rows (~50 MB). The first real backfill (7
  holdings, 3 indices, FX; full history) was 91k rows and 6.6 MB.
- **Financials:** each stock adds ~700 rows a year (annual plus 4 quarters), about 0.1 MB. So 30 stocks
  over 30 years is ~100 MB, and 100 stocks is ~300 MB. Normalizing metric names into a lookup table
  would roughly halve that if it ever matters.
