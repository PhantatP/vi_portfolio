"""
Compact, token-cheap views of the stored data for AI agents (served over MCP by api/mcp_server.py).
Everything here reads SQLite only; nothing calls Yahoo. Statement money is in millions of the
reporting currency; percentages are plain numbers (12.3 means 12.3%). Missing values are omitted.
"""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .db import get_connection
from .db_init import init_db
from .portfolio import build_portfolio_view_thb
from .prices import USD_THB, latest_prices, list_watchlist, tracked_tickers

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.json"
RETURN_WINDOWS = {"1m": 30, "3m": 91, "1y": 365, "3y": 1095, "5y": 1826}
FLOW_METRICS = ["TotalRevenue", "GrossProfit", "OperatingIncome", "NetIncome", "NormalizedIncome",
                "TotalUnusualItems", "OperatingCashFlow", "FreeCashFlow"]
KEY_METRICS = FLOW_METRICS + ["DilutedEPS", "StockholdersEquity", "TotalDebt", "CashAndCashEquivalents",
                              "OrdinarySharesNumber"]
INTERVALS = {"daily": None, "weekly": "W-FRI", "monthly": "M"}
DEFAULT_LOOKBACK_DAYS = {"daily": 91, "weekly": 365, "monthly": 1826}
MAX_POINTS = 400
STALE_DAYS = 5


def _load_targets() -> dict:
    """target_allocations from config/config.json, or {} if the file is missing (it is gitignored)."""
    try:
        return json.loads(CONFIG_PATH.read_text()).get("target_allocations", {})
    except FileNotFoundError:
        return {}


def _num(x, nd=2):
    if x is None or isinstance(x, str):
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _price(x):
    return None if x is None or pd.isna(x) else float(f"{float(x):.6g}")  # 6 significant digits


def _pct(n, d, nd=1):
    if n is None or d is None or pd.isna(n) or pd.isna(d) or d == 0:
        return None
    return _num(n / d * 100, nd)


def _m(x):
    return _num(x / 1e6, 1) if x is not None else None


def _compact(obj):
    """Drop None / NaN / empty values: agents don't pay tokens for them, and NaN isn't valid JSON."""
    if isinstance(obj, dict):
        out = {k: _compact(v) for k, v in obj.items()}
        return {k: v for k, v in out.items()
                if v is not None and v != {} and v != [] and not (isinstance(v, float) and math.isnan(v))}
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def _profile(conn, t):
    row = conn.execute("SELECT quote_type, name, sector, industry, country, currency, financial_currency "
                       "FROM profiles WHERE ticker = ?", (t,)).fetchone()
    keys = ["type", "name", "sector", "industry", "country", "currency", "reporting_currency"]
    return dict(zip(keys, row)) if row else None


def _price_stats(conn, t):
    since = (date.today() - timedelta(days=RETURN_WINDOWS["5y"] + 30)).isoformat()
    px = pd.read_sql_query("SELECT date, close FROM price_daily WHERE ticker = ? AND date >= ? ORDER BY date",
                           conn, params=(t, since)).set_index("date")["close"]
    if px.empty:
        return None
    as_of, last = px.index[-1], float(px.iloc[-1])
    as_of_d = date.fromisoformat(as_of)
    returns = {}
    for name, days in RETURN_WINDOWS.items():
        before = px[px.index <= (as_of_d - timedelta(days=days)).isoformat()]
        if not before.empty:
            returns[name] = _pct(last - before.iloc[-1], before.iloc[-1])
    year = px[px.index > (as_of_d - timedelta(days=365)).isoformat()]
    dividends = conn.execute("SELECT SUM(value) FROM corporate_actions WHERE ticker = ? AND type = 'dividend' "
                             "AND date > ?", (t, (as_of_d - timedelta(days=365)).isoformat())).fetchone()[0]
    return {
        "last": _price(last), "as_of": as_of, "return_pct": returns,
        "high_52w": _price(year.max()), "low_52w": _price(year.min()),
        "from_52w_high_pct": _pct(last - year.max(), year.max()),
        "dividend_yield_ttm_pct": _pct(dividends, last) if dividends else None,
    }


def _statement_tables(conn, t):
    df = pd.read_sql_query("SELECT period_type, period_end, metric, value FROM financials WHERE ticker = ?",
                           conn, params=(t,))

    def table(kind):  # periods x metrics, oldest first; a metric in two statements has the same value
        d = df[df.period_type == kind]
        return d.pivot_table(index="period_end", columns="metric", values="value", aggfunc="first").sort_index()

    return table("annual"), table("quarterly")


def _get(row, metric):
    v = None if row is None else row.get(metric)
    return None if v is None or pd.isna(v) else float(v)


def _fundamentals(conn, t, last_price, profile):
    annual, quarterly = _statement_tables(conn, t)
    if annual.empty and quarterly.empty:
        return None

    # flows: trailing twelve months from four consecutive quarters, else the latest fiscal year
    flows, basis = None, None
    if len(quarterly) >= 4:
        q4 = quarterly.iloc[-4:]
        if (date.fromisoformat(q4.index[-1]) - date.fromisoformat(q4.index[0])).days <= 300:
            flows = q4[[m for m in FLOW_METRICS if m in q4]].sum(min_count=4)
            basis = f"ttm to {q4.index[-1]}"
    if (flows is None or _get(flows, "TotalRevenue") is None) and not annual.empty:
        flows, basis = annual.iloc[-1], f"fy {annual.index[-1]}"
    if flows is not None and flows.dropna().empty:
        flows, basis = None, None

    def latest(metric):
        """Balance-sheet item: most recent period that has it (sparse quarterly sheets, e.g. Thai stocks)."""
        for table in (quarterly, annual):
            if metric in table and table[metric].notna().any():
                return float(table[metric].dropna().iloc[-1])
        return None

    rev, ni, fcf = _get(flows, "TotalRevenue"), _get(flows, "NetIncome"), _get(flows, "FreeCashFlow")
    # Earnings ratios use Yahoo's NormalizedIncome (excludes unusual items, e.g. GOOGL's $99B gain on
    # securities in Q2 2026) when available, so one-off gains don't make a stock look cheap.
    normalized = _get(flows, "NormalizedIncome")
    earnings = normalized if normalized is not None else ni
    equity, debt, shares = latest("StockholdersEquity"), latest("TotalDebt"), latest("OrdinarySharesNumber")

    growth = {}
    if len(annual) >= 2:
        a, p = annual.iloc[-1], annual.iloc[-2]
        r_a, r_p = _get(a, "TotalRevenue"), _get(p, "TotalRevenue")
        growth["revenue_yoy"] = _pct(r_a - r_p, r_p) if r_a is not None and r_p and r_p > 0 else None
        growth["net_income_yoy"] = _pct(_get(a, "NetIncome") - _get(p, "NetIncome"), abs(_get(p, "NetIncome"))) \
            if _get(a, "NetIncome") is not None and _get(p, "NetIncome") else None
        growth["basis"] = f"fy {annual.index[-1]} vs {annual.index[-2]}"  # not the ttm basis above
    if len(annual) >= 4:
        r_new, r_old = _get(annual.iloc[-1], "TotalRevenue"), _get(annual.iloc[-4], "TotalRevenue")
        if r_new and r_old and r_new > 0 and r_old > 0:
            growth["revenue_cagr_3y"] = _num(((r_new / r_old) ** (1 / 3) - 1) * 100, 1)

    quality = {
        "gross_margin_pct": _pct(_get(flows, "GrossProfit"), rev),
        "operating_margin_pct": _pct(_get(flows, "OperatingIncome"), rev),
        "net_margin_pct": _pct(earnings, rev),
        "fcf_margin_pct": _pct(fcf, rev),
        "roe_pct": _pct(earnings, equity) if equity and equity > 0 else None,
        "debt_to_equity": _num(debt / equity) if debt is not None and equity and equity > 0 else None,
    }

    valuation = {}
    reporting, trading = (profile or {}).get("reporting_currency"), (profile or {}).get("currency")
    if reporting and trading and reporting != trading:
        valuation["skipped"] = f"price is in {trading}, statements in {reporting}"
    elif last_price and shares and reporting:
        mcap = last_price * shares
        pe = _num(mcap / earnings, 1) if earnings and earnings > 0 else None
        pe_reported = _num(mcap / ni, 1) if ni and ni > 0 else None
        valuation = {
            "market_cap_m": _m(mcap),
            "pe": pe,
            "pe_reported": pe_reported if pe and pe_reported and abs(pe_reported / pe - 1) > 0.1 else None,
            "pb": _num(mcap / equity) if equity and equity > 0 else None,
            "ps": _num(mcap / rev) if rev and rev > 0 else None,
            "fcf_yield_pct": _pct(fcf, mcap),
        }

    return {
        "basis": basis,
        "earnings_basis": "normalized" if normalized is not None else "reported",
        "latest_annual": annual.index[-1] if not annual.empty else None,
        "latest_quarter": quarterly.index[-1] if not quarterly.empty else None,
        "size_m": {"revenue": _m(rev), "net_income": _m(ni), "normalized_income": _m(normalized),
                   "unusual_items": _m(_get(flows, "TotalUnusualItems")) or None,
                   "free_cash_flow": _m(fcf), "cash": _m(latest("CashAndCashEquivalents")), "debt": _m(debt)},
        "growth_pct": growth, "quality": quality, "valuation": valuation,
    }


def _positions():
    """Per-ticker position in THB from stored prices and FX only (never Yahoo), plus the USD/THB rate used."""
    df, total = build_portfolio_view_thb(live=False)
    if df.empty:
        return pd.DataFrame(), 0.0, None
    g = df.groupby("ticker").agg(
        quantity=("quantity", "sum"),
        value_thb=("value_thb", lambda s: s.sum(min_count=1)),  # NaN, not 0, when the price is missing
        cost_thb=("cost_thb_total", "sum"),
        price_as_of=("as_of", "first"), country=("country", "first"), sector=("sector", "first"),
        tags=("tags", "first"))
    return g, total, float(df["usd_thb"].iloc[0])


def _position_view(positions, total, t):
    if positions.empty or t not in positions.index:
        return None
    p = positions.loc[t]
    return {"quantity": _num(p.quantity, 6), "value_thb": _num(p.value_thb, 0), "cost_thb": _num(p.cost_thb, 0),
            "pl_pct": _pct(p.value_thb - p.cost_thb, p.cost_thb), "weight_pct": _pct(p.value_thb, total),
            "price_missing": True if pd.isna(p.value_thb) else None}


def _notes(conn, t):
    cur = conn.execute("SELECT n.my_summary, n.business_model, n.revenue_model, n.future_view, n.risk_view, "
                       "n.rating, n.growth_dividend, n.updated_at FROM notes n JOIN assets a ON a.id = n.asset_id "
                       "WHERE a.ticker = ?", (t,))
    row = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], row)) if row else None


def _brief(conn, t, positions, total):
    profile = _profile(conn, t)
    price = _price_stats(conn, t)
    fundamentals = _fundamentals(conn, t, price and price["last"], profile)
    position = _position_view(positions, total, t)
    if not (profile or price or fundamentals or position):
        return None
    head = dict(profile or {})
    if head.get("reporting_currency") == head.get("currency"):
        head.pop("reporting_currency", None)
    return _compact({"ticker": t, **head, "price": price, "fundamentals": fundamentals,
                     "position": position, "notes": _notes(conn, t)})


def ticker_brief(ticker: str) -> dict | None:
    """Profile, price stats, fundamentals and your position for one ticker; None if nothing is stored."""
    init_db()
    positions, total, _ = _positions()
    conn = get_connection()
    try:
        return _brief(conn, ticker.strip().upper(), positions, total)
    finally:
        conn.close()


def watchlist_view() -> list[dict]:
    init_db()
    positions, total, _ = _positions()
    conn = get_connection()
    try:
        out = []
        for w in list_watchlist():
            b = _brief(conn, w["ticker"], positions, total) or {}
            price, fund = b.get("price", {}), b.get("fundamentals", {})
            out.append(_compact({
                "ticker": w["ticker"], "name": b.get("name"), "type": b.get("type"), "reason": w["reason"],
                "last": price.get("last"), "as_of": price.get("as_of"),
                "return_1y_pct": price.get("return_pct", {}).get("1y"),
                "from_52w_high_pct": price.get("from_52w_high_pct"),
                "pe": fund.get("valuation", {}).get("pe"),
            }))
        return out
    finally:
        conn.close()


def _text(x):
    """A usable string, or None (pandas gives NaN, not None, for missing text)."""
    return x if isinstance(x, str) and x.strip() else None


def _country_bucket(ticker, *countries):
    c = next((_text(x) for x in countries if _text(x)), "").strip().lower()
    if ticker.endswith(".BK") or c in ("th", "thailand"):
        return "TH"
    if c in ("us", "usa", "united states"):
        return "US"
    return "OTHER" if c else "UNKNOWN"


def _style_bucket(tags):
    tags = (tags or "").lower()
    return "growth" if "growth" in tags else "dividend" if "dividend" in tags else "untagged"


def portfolio_summary() -> dict:
    """Totals in THB, positions by weight, and allocation against config/config.json targets."""
    init_db()
    positions, total, usd_thb_used = _positions()
    if positions.empty:
        return {"positions": []}
    targets = _load_targets()
    conn = get_connection()
    try:
        prof = {t: _profile(conn, t) or {} for t in positions.index}
    finally:
        conn.close()

    cost = float(positions.cost_thb.sum())
    rows = positions.assign(
        country_bucket=[_country_bucket(t, positions.loc[t, "country"], prof[t].get("country")) for t in positions.index],
        style=[_style_bucket(_text(x)) for x in positions.tags],
        sector_name=[_text(positions.loc[t, "sector"]) or prof[t].get("sector") or "Unknown" for t in positions.index],
    )

    def split(col):
        return {k: _pct(v, total) for k, v in rows.groupby(col).value_thb.sum().sort_values(ascending=False).items()}

    priced = rows[rows.value_thb.notna()]
    priced_cost = float(priced.cost_thb.sum())  # P/L only over positions that have a price
    usd_thb = latest_prices([USD_THB])
    return _compact({
        "total_value_thb": _num(total, 0), "total_cost_thb": _num(cost, 0),
        "unrealized_pl_thb": _num(total - priced_cost, 0), "unrealized_pl_pct": _pct(total - priced_cost, priced_cost),
        "positions_missing_price": sorted(rows.index[rows.value_thb.isna()]),
        "note": None if targets else "No allocation targets: config/config.json is missing.",
        "usd_thb": {"rate": _price(usd_thb_used), "as_of": None if usd_thb.empty else usd_thb.as_of.iloc[0]},
        "oldest_price_as_of": rows.price_as_of.dropna().min() if rows.price_as_of.notna().any() else None,
        "positions": [
            {"ticker": t, "weight_pct": _pct(r.value_thb, total), "value_thb": _num(r.value_thb, 0),
             "pl_pct": _pct(r.value_thb - r.cost_thb, r.cost_thb), "price_as_of": r.price_as_of,
             "price_missing": True if pd.isna(r.value_thb) else None}
            for t, r in rows.sort_values("value_thb", ascending=False).iterrows()],
        "allocation_pct": {
            "country": split("country_bucket"),
            "country_target": {k: _num(v * 100, 1) for k, v in targets.get("country", {}).items()},
            "style": split("style"),
            "style_target": {k: _num(v * 100, 1) for k, v in targets.get("tag", {}).items()},
            "btc": _pct(rows[[t.startswith("BTC") for t in rows.index]].value_thb.sum(), total),
            "btc_max": _num(targets["btc_max"] * 100, 1) if "btc_max" in targets else None,
            "sector": split("sector_name"),
        },
    })


def price_history(ticker: str, start: str | None = None, end: str | None = None, interval: str = "monthly") -> dict:
    """Closes (split-adjusted, not dividend-adjusted) sampled at the last trading day of each period."""
    if interval not in INTERVALS:
        raise ValueError(f"interval must be one of {list(INTERVALS)}")
    t = ticker.strip().upper()
    end = end or date.today().isoformat()
    start = start or (date.fromisoformat(end) - timedelta(days=DEFAULT_LOOKBACK_DAYS[interval])).isoformat()
    init_db()
    conn = get_connection()
    try:
        px = pd.read_sql_query("SELECT date, close FROM price_daily WHERE ticker = ? AND date BETWEEN ? AND ? "
                               "ORDER BY date", conn, params=(t, start, end))
        currency = (_profile(conn, t) or {}).get("currency")
    finally:
        conn.close()
    if INTERVALS[interval] and not px.empty:
        period = pd.to_datetime(px.date).dt.to_period(INTERVALS[interval])
        px = px.groupby(period).tail(1)
    points = [[d, _price(c)] for d, c in zip(px.date, px.close)]
    truncated = len(points) > MAX_POINTS
    return _compact({"ticker": t, "interval": interval, "currency": currency, "from": start, "to": end,
                     "truncated_to_latest": MAX_POINTS if truncated else None,
                     "points": points[-MAX_POINTS:]})


def _scale(metric, v):
    if v is None or pd.isna(v):
        return None
    if "EPS" in metric or "PerShare" in metric or "Rate" in metric:
        return _num(v, 4)
    return _num(v / 1e6, 1)


def financials_table(ticker: str, period_type: str = "annual", metrics: list[str] | None = None,
                     periods: int = 4, list_available: bool = False) -> dict:
    """Stored statement line items, oldest period first."""
    if period_type not in ("annual", "quarterly"):
        raise ValueError("period_type must be 'annual' or 'quarterly'")
    t = ticker.strip().upper()
    init_db()
    conn = get_connection()
    try:
        annual, quarterly = _statement_tables(conn, t)
        reporting = (_profile(conn, t) or {}).get("reporting_currency")
    finally:
        conn.close()
    table = (annual if period_type == "annual" else quarterly).iloc[-max(1, periods):]
    names = metrics or [m for m in KEY_METRICS if m in table.columns]
    return _compact({
        "ticker": t, "period_type": period_type, "reporting_currency": reporting,
        "unit": "millions, except per-share and rate values",
        "periods": list(table.index),
        "metrics": {m: [_scale(m, v) for v in table[m]] for m in names if m in table.columns},
        "unknown_metrics": [m for m in names if m not in table.columns],
        "available_metrics": sorted(table.columns) if list_available else len(table.columns),
    })


def data_status() -> dict:
    """Freshness of the stored data, so an agent can tell whether to trust it."""
    init_db()
    tickers = tracked_tickers()
    conn = get_connection()
    try:
        jobs = {}
        for job, status, started, finished, detail in conn.execute(
                "SELECT job, status, started_at, finished_at, detail FROM job_runs "
                "WHERE id IN (SELECT MAX(id) FROM job_runs GROUP BY job)"):
            try:
                d = json.loads(detail or "{}")
            except json.JSONDecodeError:
                d = {"message": detail}
            jobs[job] = _compact({"status": status, "finished_at": finished or started,
                                  "problems": {k: d[k] for k in ("missing", "errors", "no_statements", "message")
                                               if d.get(k)}})
        with_statements = conn.execute("SELECT COUNT(DISTINCT ticker) FROM financials").fetchone()[0]
    finally:
        conn.close()
    latest = latest_prices(tickers)
    cutoff = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
    return _compact({
        "today": date.today().isoformat(), "jobs": jobs, "tracked_tickers": len(tickers),
        "tickers_with_statements": with_statements,
        "prices_newest": latest.as_of.max() if not latest.empty else None,
        "prices_stale_or_missing": sorted(set(tickers) - set(latest[latest.as_of >= cutoff].ticker)),
    })
