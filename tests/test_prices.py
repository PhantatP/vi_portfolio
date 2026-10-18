"""Migrations, price refresh (against a fake yf.download) and the DB-backed price readers."""
import sqlite3
from datetime import date

import pandas as pd
import pytest

import core.db
import core.db_init
import core.fx
import core.portfolio
import core.prices


def _frame(rows):
    """rows: [(date, close)] or [(date, close, dividend, split)]"""
    rows = [r + (0.0, 0.0) if len(r) == 2 else r for r in rows]
    return pd.DataFrame(
        {"Close": [r[1] for r in rows], "Volume": 100.0,
         "Dividends": [r[2] for r in rows], "Stock Splits": [r[3] for r in rows]},
        index=pd.DatetimeIndex([r[0] for r in rows], name="Date"))


class FakeYahoo:
    def __init__(self):
        self.data = {}             # ticker -> frame Yahoo would return for period="max"
        self.no_full_history = set()
        self.flat_single = False   # older yfinance: one ticker comes back without the ticker column level
        self.calls = []

    def download(self, tickers, start=None, period=None, **kwargs):
        self.calls.append((sorted(tickers), start, period))
        frames = {}
        for t in tickers:
            if t not in self.data or (period == "max" and t in self.no_full_history):
                continue
            f = self.data[t]
            frames[t] = f[f.index >= start] if start else f
        if self.flat_single and len(tickers) == 1:
            return next(iter(frames.values()), pd.DataFrame())
        # union of dates across tickers, NaN where a ticker didn't trade, like the real batch download
        return pd.concat(frames, axis=1) if frames else pd.DataFrame()


@pytest.fixture
def yahoo(tmp_path, monkeypatch):
    monkeypatch.setattr(core.db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(core.db_init, "_schema_ready", False)
    fake = FakeYahoo()
    monkeypatch.setattr(core.prices.yf, "download", fake.download)
    monkeypatch.setattr(core.portfolio, "_fetch_live_price", lambda t: pytest.fail(f"live fetch for {t}"))
    return fake


def _sql(query, params=()):
    con = sqlite3.connect(core.db.DB_PATH)
    rows = con.execute(query, params).fetchall()
    con.commit()
    con.close()
    return rows


def _hold(ticker, qty):
    core.db_init.init_db()
    asset_id = _sql("INSERT INTO assets (ticker) VALUES (?) RETURNING id", (ticker,))[0][0]
    _sql("INSERT INTO holdings (asset_id, broker, quantity, avg_price, currency) VALUES (?, 'Dime', ?, 1, 'THB')",
         (asset_id, qty))


def _closes(ticker):
    return _sql("SELECT date, close FROM price_daily WHERE ticker = ? ORDER BY date", (ticker,))


def test_fresh_db_is_fully_migrated(yahoo):
    core.db_init.init_db()
    assert _sql("PRAGMA user_version")[0][0] == len(core.db_init.MIGRATIONS)
    assert _sql("PRAGMA journal_mode")[0][0] == "wal"
    assert {r[0] for r in _sql("SELECT ticker FROM watchlist")} == set(core.db_init.BENCHMARKS)


def test_unversioned_legacy_db_keeps_its_data(yahoo, monkeypatch):
    con = sqlite3.connect(core.db.DB_PATH)  # a DB made by the old init_db: no user_version, no import columns
    con.executescript(core.db_init.SCHEMA_SQL)
    con.execute("INSERT INTO assets (ticker) VALUES ('VOO')")
    con.commit()
    con.close()

    core.db_init.init_db()
    monkeypatch.setattr(core.db_init, "_schema_ready", False)
    core.db_init.init_db()  # second run is a no-op

    assert _sql("PRAGMA user_version")[0][0] == len(core.db_init.MIGRATIONS)
    assert _sql("SELECT ticker FROM assets") == [("VOO",)]
    assert "external_id" in {r[1] for r in _sql("PRAGMA table_info(transactions)")}
    assert _sql("SELECT COUNT(*) FROM watchlist")[0][0] == len(core.db_init.BENCHMARKS)


def test_tracked_tickers_are_held_plus_watched_plus_fx(yahoo):
    _hold("aapl", 2)
    _hold("SOLD", 0)
    core.prices.add_to_watchlist("cpall.bk")
    assert core.prices.tracked_tickers() == sorted(
        {"AAPL", "CPALL.BK", "USDTHB=X", *core.db_init.BENCHMARKS})


def test_refresh_backfills_then_updates_without_duplicates(yahoo):
    _hold("AAPL", 1)
    yahoo.data["AAPL"] = _frame([("2026-10-01", 200.0), ("2026-10-02", 201.0, 0.25, 0.0)])
    yahoo.data["USDTHB=X"] = _frame([("2026-10-01", 33.0), ("2026-10-02", 33.1)])

    first = core.prices.refresh_prices()
    assert first["status"] == "ok"
    assert set(first["backfilled"]) == {"AAPL", "USDTHB=X"}
    assert set(first["missing"]) == set(core.db_init.BENCHMARKS)  # no fake data for them
    assert yahoo.calls[-1][2] == "max"
    assert _sql("SELECT type, value FROM corporate_actions WHERE ticker = 'AAPL'") == [("dividend", 0.25)]

    core.prices.refresh_prices()  # same data again
    assert _closes("AAPL") == [("2026-10-01", 200.0), ("2026-10-02", 201.0)]

    # next day arrives, and Yahoo corrects the previous close
    yahoo.data["AAPL"] = _frame([("2026-10-01", 200.0), ("2026-10-02", 201.5), ("2026-10-05", 205.0)])
    core.prices.refresh_prices()
    assert _closes("AAPL") == [("2026-10-01", 200.0), ("2026-10-02", 201.5), ("2026-10-05", 205.0)]
    _, start, period = [c for c in yahoo.calls if c[0] == ["AAPL", "USDTHB=X"]][-1]
    assert (start, period) == ("2026-09-25", None)  # last stored date minus OVERLAP_DAYS
    assert _sql("SELECT status FROM job_runs ORDER BY id") == [("ok",)] * 3


def test_new_split_refetches_full_history(yahoo):
    _hold("NVDA", 1)
    yahoo.data["NVDA"] = _frame([("2026-09-01", 400.0), ("2026-09-02", 404.0)])
    core.prices.refresh_prices()

    # 4:1 split: Yahoo re-bases all past closes
    yahoo.data["NVDA"] = _frame([("2026-09-01", 100.0), ("2026-09-02", 101.0), ("2026-09-03", 102.0, 0.0, 4.0)])
    result = core.prices.refresh_prices()

    assert result["rebased"] == ["NVDA"]
    assert _closes("NVDA") == [("2026-09-01", 100.0), ("2026-09-02", 101.0), ("2026-09-03", 102.0)]
    assert _sql("SELECT date, value FROM corporate_actions WHERE type = 'split'") == [("2026-09-03", 4.0)]

    n = len(yahoo.calls)
    core.prices.refresh_prices()  # split is known now: no second full re-fetch
    assert not [c for c in yahoo.calls[n:] if c[2] == "max" and "NVDA" in c[0]]


def test_split_waits_for_full_history(yahoo):
    _hold("NVDA", 1)
    yahoo.data["NVDA"] = _frame([("2026-08-31", 400.0), ("2026-09-01", 404.0)])
    core.prices.refresh_prices()

    yahoo.data["NVDA"] = _frame([("2026-08-31", 100.0), ("2026-09-01", 101.0), ("2026-09-03", 102.0, 0.0, 4.0)])
    yahoo.no_full_history.add("NVDA")
    result = core.prices.refresh_prices()

    assert "NVDA" in result["missing"]
    assert _closes("NVDA") == [("2026-08-31", 400.0), ("2026-09-01", 404.0)]  # old basis left intact
    assert _sql("SELECT COUNT(*) FROM corporate_actions")[0][0] == 0


def test_late_rebase_is_caught(yahoo):
    _hold("NVDA", 1)
    yahoo.data["NVDA"] = _frame([("2026-09-01", 400.0), ("2026-09-02", 404.0)])
    core.prices.refresh_prices()

    # Yahoo reports the split day before re-basing older closes
    yahoo.data["NVDA"] = _frame([("2026-09-01", 400.0), ("2026-09-02", 404.0), ("2026-09-03", 102.0, 0.0, 4.0)])
    assert core.prices.refresh_prices()["rebased"] == []

    yahoo.data["NVDA"] = _frame([("2026-09-01", 100.0), ("2026-09-02", 101.0), ("2026-09-03", 102.0, 0.0, 4.0)])
    assert core.prices.refresh_prices()["rebased"] == ["NVDA"]
    assert _closes("NVDA") == [("2026-09-01", 100.0), ("2026-09-02", 101.0), ("2026-09-03", 102.0)]


def test_intraday_move_on_last_stored_day_is_not_a_rebase(yahoo):
    _hold("RKLB", 1)
    yahoo.data["RKLB"] = _frame([("2026-09-01", 50.0), ("2026-09-02", 50.0)])  # 09-02 stored mid-session
    core.prices.refresh_prices()
    yahoo.data["RKLB"] = _frame([("2026-09-01", 50.0), ("2026-09-02", 60.0)])
    assert core.prices.refresh_prices()["rebased"] == []
    assert _closes("RKLB")[-1] == ("2026-09-02", 60.0)


def test_single_ticker_with_flat_columns(yahoo):
    yahoo.flat_single = True
    _hold("VOO", 1)
    core.prices.remove_from_watchlist("^GSPC")
    core.prices.remove_from_watchlist("^IXIC")
    core.prices.remove_from_watchlist("^SET.BK")
    yahoo.data["VOO"] = _frame([("2026-10-01", 600.0)])
    yahoo.data["USDTHB=X"] = _frame([("2026-10-01", 33.0)])
    core.prices.BATCH, batch = 1, core.prices.BATCH  # one ticker per call
    try:
        assert core.prices.refresh_prices()["missing"] == []
    finally:
        core.prices.BATCH = batch
    assert _closes("VOO") == [("2026-10-01", 600.0)]


def test_downloads_are_batched_and_grouped_by_last_date(yahoo, monkeypatch):
    monkeypatch.setattr(core.prices, "BATCH", 2)
    for t in ("A", "B", "C"):
        _hold(t, 1)
        yahoo.data[t] = _frame([("2026-10-01", 10.0)])
    core.prices.refresh_prices()
    assert all(len(tickers) <= 2 for tickers, _, _ in yahoo.calls)

    # C stops updating; A and B keep a narrow window
    yahoo.data["A"] = yahoo.data["B"] = _frame([("2026-10-01", 10.0), ("2026-10-02", 11.0)])
    core.prices.refresh_prices()
    yahoo.calls.clear()
    core.prices.refresh_prices()
    starts = {tuple(tickers): start for tickers, start, _ in yahoo.calls if start}
    assert starts[("A", "B")] == "2026-09-25" and starts[("C",)] == "2026-09-24"


def test_no_data_at_all_is_an_error(yahoo):
    result = core.prices.refresh_prices()
    assert result["status"] == "error"
    assert _sql("SELECT status FROM job_runs") == [("error",)]


def test_portfolio_and_fx_read_stored_prices(yahoo, monkeypatch):
    _hold("AAPL", 1)
    yahoo.data["AAPL"] = _frame([("2026-10-01", 200.0), ("2026-10-02", 201.0)])
    yahoo.data["USDTHB=X"] = _frame([(date.today().isoformat(), 33.1)])  # fresh, so no live fetch
    core.prices.refresh_prices()
    monkeypatch.setattr(core.fx.yf, "Ticker", lambda t: pytest.fail("live FX fetch"))

    prices = core.portfolio.fetch_latest_prices(["aapl"])
    assert prices.to_dict("records") == [{"ticker": "AAPL", "price": 201.0, "as_of": "2026-10-02"}]
    assert core.fx.fetch_usd_thb_rate() == 33.1


def test_stale_stored_fx_prefers_live_but_beats_default(yahoo, monkeypatch):
    yahoo.data["USDTHB=X"] = _frame([("2020-01-02", 30.0)])
    core.prices.refresh_prices()

    class Live:
        fast_info = {"last_price": 33.5}
    monkeypatch.setattr(core.fx.yf, "Ticker", lambda t: Live())
    assert core.fx.fetch_usd_thb_rate() == 33.5

    monkeypatch.setattr(core.fx.yf, "Ticker", lambda t: (_ for _ in ()).throw(RuntimeError("offline")))
    assert core.fx.fetch_usd_thb_rate() == 30.0


def test_unstored_ticker_falls_back_to_live(yahoo, monkeypatch):
    monkeypatch.setattr(core.portfolio, "_fetch_live_price", lambda t: 50.0)
    prices = core.portfolio.fetch_latest_prices(["NEW"])
    assert prices[["ticker", "price"]].to_dict("records") == [{"ticker": "NEW", "price": 50.0}]


def test_watchlist_add_and_remove(yahoo):
    core.prices.add_to_watchlist(" cpall.bk ", "cheap retailer")
    watched = {w["ticker"]: w["reason"] for w in core.prices.list_watchlist()}
    assert watched["CPALL.BK"] == "cheap retailer"
    assert core.prices.remove_from_watchlist("CPALL.BK")
    assert not core.prices.remove_from_watchlist("CPALL.BK")


def test_checked_add_rejects_unknown_symbols_and_backfills_known_ones(yahoo):
    yahoo.data["CPALL.BK"] = _frame([("2026-10-01", 40.0), ("2026-10-02", 41.0)])
    with pytest.raises(ValueError, match="Yahoo has no prices for CPAL.BK"):
        core.prices.add_checked_to_watchlist("cpal.bk")
    assert "CPAL.BK" not in {w["ticker"] for w in core.prices.list_watchlist()}

    assert core.prices.add_checked_to_watchlist(" cpall.bk ", "cheap retailer") == "CPALL.BK"
    assert _closes("CPALL.BK") == [("2026-10-01", 40.0), ("2026-10-02", 41.0)]  # no wait for the refresh

    calls = len(yahoo.calls)
    core.prices.add_checked_to_watchlist("CPALL.BK", "new reason")  # already stored: no Yahoo call
    assert len(yahoo.calls) == calls
    assert {w["ticker"]: w["reason"] for w in core.prices.list_watchlist()}["CPALL.BK"] == "new reason"
