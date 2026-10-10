"""End to end: the real API app on a local port, driven by the MCP client over streamable HTTP."""
import asyncio
import json
import socket
import sqlite3
import threading
import time
from datetime import date, timedelta

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import core.db
import core.db_init
import core.portfolio


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(core.db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(core.db_init, "_schema_ready", False)
    monkeypatch.setattr(core.portfolio, "_fetch_live_price", lambda t: pytest.fail(f"live fetch for {t}"))
    core.db_init.init_db()
    con = sqlite3.connect(core.db.DB_PATH)
    asset_id = con.execute("INSERT INTO assets (ticker, country) VALUES ('VOO', 'United States') RETURNING id").fetchone()[0]
    con.execute("INSERT INTO holdings (asset_id, broker, quantity, avg_price, currency) VALUES (?, 'Dime', 2, 20000, 'THB')",
                (asset_id,))
    day = lambda n: (date.today() - timedelta(days=n)).isoformat()  # relative: stored FX must stay fresh
    con.executemany("INSERT INTO price_daily (ticker, date, close, source) VALUES (?, ?, ?, 'test')",
                    [("VOO", day(2), 600.0), ("VOO", day(1), 610.0), ("USDTHB=X", day(1), 33.0)])
    con.execute("INSERT INTO profiles (ticker, quote_type, name, currency, source) VALUES "
                "('VOO', 'ETF', 'Vanguard S&P 500 ETF', 'USD', 'test')")
    con.commit()
    con.close()

    from api.main import app
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


async def _session_calls(url, calls):
    async with streamable_http_client(f"{url}/mcp") as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            results = []  # (is_error, text), in call order
            for name, args in calls:
                r = await session.call_tool(name, args)
                results.append((r.is_error, r.content[0].text))
            return tools, results


def test_tools_are_listed_read_only_and_answer_from_the_db(server):
    tools, results = asyncio.run(_session_calls(server, [
        ("get_portfolio", {}),
        ("get_ticker_brief", {"ticker": "voo"}),
        ("get_ticker_brief", {"ticker": "NOPE"}),
        ("get_price_history", {"ticker": "VOO", "interval": "yearly"}),
    ]))
    assert {t.name for t in tools.tools} == {"get_portfolio", "get_ticker_brief", "get_watchlist",
                                             "get_price_history", "get_financials", "get_data_status"}
    assert all(t.annotations.read_only_hint for t in tools.tools)
    (p_err, p_text), (b_err, b_text), (_, missing_text), (h_err, h_text) = results

    portfolio = json.loads(p_text)
    assert not p_err
    assert portfolio["total_value_thb"] == 2 * 610 * 33  # USD price converted with the stored rate
    assert portfolio["positions"][0]["ticker"] == "VOO"

    brief = json.loads(b_text)
    assert not b_err
    assert brief["price"]["last"] == 610.0 and brief["position"]["weight_pct"] == 100.0
    assert "watch-add NOPE" in json.loads(missing_text)["error"]

    assert h_err and "'daily', 'weekly' or 'monthly'" in h_text  # the agent is told the valid values

    # the REST API on the same port is untouched by the mount
    # (one test per process: the MCP session manager can only be started once)
    assert httpx.get(f"{server}/").json()["status"] == "online"
    assert httpx.get(f"{server}/api/holdings").json()[0]["ticker"] == "VOO"
    assert httpx.post(f"{server}/api/holdings").status_code == 405  # FastAPI's own errors, not MCP's 404
