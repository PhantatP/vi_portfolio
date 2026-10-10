"""
MCP server for AI agents: read-only tools over the stored data (core/briefs.py). Mounted into the
FastAPI app in api/main.py, so it shares the API's port: http://<host>:8000/mcp
"""
import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from core import briefs

INSTRUCTIONS = """Read-only data from the user's value-investing portfolio tracker (SQLite, refreshed by
scheduled jobs; tools never call the market live).
- Start with get_portfolio or get_ticker_brief; use get_price_history / get_financials only for detail.
- Prices are daily closes, split-adjusted but not dividend-adjusted, in the ticker's trading currency.
  Portfolio values are in THB.
- Statement money is in millions of the reporting currency, which can differ from the trading currency
  (e.g. TM: USD price, JPY statements). Percentages are plain numbers: 12.3 means 12.3%.
- P/E uses normalized income (excludes unusual items) when available; pe_reported is shown when it
  differs by more than 10%.
- Only tracked tickers (held, or on the watchlist) have data. To add one, the user runs
  `python app/cli.py watch-add TICKER`; data appears after the next refresh.
- Check get_data_status if freshness matters: prices refresh hourly, statements weekly."""

mcp = MCPServer("vi-portfolio", instructions=INSTRUCTIONS)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)  # compact: fewer tokens


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_portfolio() -> str:
    """Portfolio totals (THB), positions by weight with P/L, and allocation by country, style and
    sector against the user's targets."""
    return _json(briefs.portfolio_summary())


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_ticker_brief(ticker: str) -> str:
    """One ticker in ~250 tokens: profile, price returns and 52-week range, TTM fundamentals
    (growth, margins, ROE, leverage, valuation), the user's position, and the user's notes."""
    brief = briefs.ticker_brief(ticker)
    if brief is None:
        t = ticker.strip().upper()
        return _json({"error": f"{t} is not tracked. Ask the user to run: python app/cli.py watch-add {t}"})
    return _json(brief)


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_watchlist() -> str:
    """Watched tickers (including benchmark indices) with last price, 1-year return, distance from
    the 52-week high and P/E."""
    return _json(briefs.watchlist_view())


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_price_history(ticker: str, start: str | None = None, end: str | None = None,
                      interval: Literal["daily", "weekly", "monthly"] = "monthly") -> str:
    """Closing prices sampled daily, weekly or monthly (last trading day of each period).
    Dates are YYYY-MM-DD. Defaults: last 5 years monthly, 1 year weekly, 3 months daily.
    At most 400 points (the latest are kept)."""
    return _json(briefs.price_history(ticker, start, end, interval))


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_financials(ticker: str, period_type: Literal["annual", "quarterly"] = "annual",
                   metrics: list[str] | None = None, periods: int = 4, list_available: bool = False) -> str:
    """Stored statement line items, oldest period first. period_type: annual or quarterly.
    metrics: Yahoo raw keys (e.g. TotalRevenue, NetIncome, FreeCashFlow); default is a key set.
    list_available=true returns every metric name stored for the ticker."""
    return _json(briefs.financials_table(ticker, period_type, metrics, periods, list_available))


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def get_data_status() -> str:
    """Freshness of the stored data: last run of each refresh job, problems it reported, and
    tickers whose prices are stale or missing."""
    return _json(briefs.data_status())


# Stateless JSON responses: plain request/response, no session state to keep.
# host="0.0.0.0" turns off the SDK's localhost-only Host check so the laptop can reach the Jetson.
# The REST API on the same port is already open to the LAN, so this exposes nothing new.
mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                  host="0.0.0.0")
