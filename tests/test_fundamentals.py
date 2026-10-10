"""Fundamentals refresh against a fake yf.Ticker: profiles, statements, kept history, per-ticker failures."""
import sqlite3

import pandas as pd
import pytest

import core.db
import core.db_init
import core.fundamentals
import core.prices


def _stmt(periods):
    """periods: {'2025-12-31': {'TotalRevenue': 100.0, ...}} -> Yahoo layout (metrics x period ends)"""
    return pd.DataFrame({pd.Timestamp(d): m for d, m in periods.items()})


class FakeTicker:
    def __init__(self, info=None, statements=None, error=None):
        self.info_ = info or {}
        self.statements = statements or {}  # (method, freq) -> frame
        self.error = error
        self.calls = []

    @property
    def info(self):
        if self.error:
            raise self.error
        return self.info_

    def _get(self, method, freq):
        self.calls.append((method, freq))
        # while "Yahoo" is being called, another process must be able to write (no lock held)
        other = sqlite3.connect(core.db.DB_PATH, timeout=0)
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
        other.close()
        return self.statements.get((method, freq), pd.DataFrame())

    def get_income_stmt(self, pretty, freq):
        return self._get("income", freq)

    def get_balance_sheet(self, pretty, freq):
        return self._get("balance", freq)

    def get_cashflow(self, pretty, freq):
        return self._get("cashflow", freq)


@pytest.fixture
def yahoo(tmp_path, monkeypatch):
    monkeypatch.setattr(core.db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(core.db_init, "_schema_ready", False)
    monkeypatch.setattr(core.fundamentals, "PAUSE_SECONDS", 0)
    tickers = {}
    monkeypatch.setattr(core.fundamentals.yf, "Ticker", lambda t: tickers[t])
    core.db_init.init_db()
    # only the tickers each test adds: drop the seeded benchmarks; USDTHB=X is always tracked
    for t in core.db_init.BENCHMARKS:
        core.prices.remove_from_watchlist(t)
    tickers["USDTHB=X"] = FakeTicker({"quoteType": "CURRENCY", "currency": "THB"})
    return tickers


def _sql(query, params=()):
    con = sqlite3.connect(core.db.DB_PATH)
    rows = con.execute(query, params).fetchall()
    con.close()
    return rows


EQUITY = {"quoteType": "EQUITY", "longName": "Alphabet Inc.", "sector": "Communication Services",
          "industry": "Internet Content", "country": "United States", "currency": "USD",
          "longBusinessSummary": "Search and cloud."}


def test_equity_gets_profile_and_all_statements(yahoo):
    core.prices.add_to_watchlist("GOOGL")
    yahoo["GOOGL"] = FakeTicker(EQUITY, {
        ("income", "yearly"): _stmt({"2025-12-31": {"TotalRevenue": 400.0, "NetIncome": 100.0}}),
        ("income", "quarterly"): _stmt({"2026-06-30": {"TotalRevenue": 110.0, "NetIncome": float("nan")}}),
        ("balance", "yearly"): _stmt({"2025-12-31": {"StockholdersEquity": 350.0}}),
    })

    result = core.fundamentals.refresh_fundamentals()

    assert result["status"] == "ok" and result["errors"] == {}
    assert result["profiles"] == 2  # GOOGL + USDTHB=X
    assert _sql("SELECT name, sector, quote_type, summary FROM profiles WHERE ticker = 'GOOGL'") == [
        ("Alphabet Inc.", "Communication Services", "EQUITY", "Search and cloud.")]
    assert sorted(_sql("SELECT statement, period_type, period_end, metric, value FROM financials")) == [
        ("balance", "annual", "2025-12-31", "StockholdersEquity", 350.0),
        ("income", "annual", "2025-12-31", "NetIncome", 100.0),
        ("income", "annual", "2025-12-31", "TotalRevenue", 400.0),
        ("income", "quarterly", "2026-06-30", "TotalRevenue", 110.0),  # NaN NetIncome skipped
    ]
    assert len(yahoo["GOOGL"].calls) == 6  # 3 statements x annual/quarterly


def test_non_equities_get_profile_only(yahoo):
    core.prices.add_to_watchlist("VOO")
    yahoo["VOO"] = FakeTicker({"quoteType": "ETF", "longName": "Vanguard S&P 500 ETF"})
    result = core.fundamentals.refresh_fundamentals()
    assert yahoo["VOO"].calls == [] and yahoo["USDTHB=X"].calls == []
    assert result["rows"] == 0 and result["no_statements"] == []
    assert _sql("SELECT ticker, quote_type FROM profiles ORDER BY ticker") == [("USDTHB=X", "CURRENCY"), ("VOO", "ETF")]


def test_restatements_overwrite_and_dropped_periods_are_kept(yahoo):
    core.prices.add_to_watchlist("GOOGL")
    yahoo["GOOGL"] = FakeTicker(EQUITY, {("income", "yearly"): _stmt({
        "2021-12-31": {"TotalRevenue": 250.0}, "2022-12-31": {"TotalRevenue": 280.0}})})
    core.fundamentals.refresh_fundamentals()

    # a year later: 2021 no longer served, 2022 restated, 2023 new
    yahoo["GOOGL"] = FakeTicker(EQUITY, {("income", "yearly"): _stmt({
        "2022-12-31": {"TotalRevenue": 282.0}, "2023-12-31": {"TotalRevenue": 300.0}})})
    core.fundamentals.refresh_fundamentals()

    assert _sql("SELECT period_end, value FROM financials ORDER BY period_end") == [
        ("2021-12-31", 250.0), ("2022-12-31", 282.0), ("2023-12-31", 300.0)]


def test_one_failing_ticker_does_not_stop_the_rest(yahoo):
    core.prices.add_to_watchlist("BAD")
    core.prices.add_to_watchlist("GOOGL")
    yahoo["BAD"] = FakeTicker(error=RuntimeError("rate limited"))
    yahoo["GOOGL"] = FakeTicker(EQUITY, {("income", "yearly"): _stmt({"2025-12-31": {"TotalRevenue": 400.0}})})

    result = core.fundamentals.refresh_fundamentals()

    assert result["status"] == "partial"  # not "ok": the CLI exits non-zero so systemd shows it
    assert list(result["errors"]) == ["BAD"]
    assert _sql("SELECT COUNT(*) FROM financials WHERE ticker = 'GOOGL'")[0][0] == 1
    assert _sql("SELECT status FROM job_runs WHERE job = 'fundamentals_refresh'") == [("partial",)]


def test_every_equity_empty_is_an_error(yahoo):
    core.prices.add_to_watchlist("GOOGL")
    yahoo["GOOGL"] = FakeTicker(EQUITY)  # profile fine, statements empty (e.g. swallowed rate limit)
    result = core.fundamentals.refresh_fundamentals()
    assert result["status"] == "error" and result["no_statements"] == ["GOOGL"]


def test_profile_keeps_reporting_currency_and_survives_degraded_response(yahoo):
    core.prices.add_to_watchlist("TM")
    full = {**EQUITY, "longName": "Toyota Motor Corporation", "currency": "USD", "financialCurrency": "JPY"}
    yahoo["TM"] = FakeTicker(full, {("income", "yearly"): _stmt({"2026-03-31": {"TotalRevenue": 48e12}})})
    core.fundamentals.refresh_fundamentals()

    yahoo["TM"] = FakeTicker({"quoteType": "EQUITY", "currency": "USD"},  # sector, summary etc. missing
                             {("income", "yearly"): _stmt({"2026-03-31": {"TotalRevenue": 48e12}})})
    core.fundamentals.refresh_fundamentals()

    assert _sql("SELECT name, currency, financial_currency, sector, summary FROM profiles WHERE ticker = 'TM'") == [
        ("Toyota Motor Corporation", "USD", "JPY", "Communication Services", "Search and cloud.")]


def test_everything_failing_is_an_error(yahoo):
    yahoo["USDTHB=X"] = FakeTicker(error=RuntimeError("offline"))
    assert core.fundamentals.refresh_fundamentals()["status"] == "error"
    assert _sql("SELECT status FROM job_runs WHERE job = 'fundamentals_refresh'") == [("error",)]


def test_unknown_symbol_stores_no_profile(yahoo):
    core.prices.add_to_watchlist("TYPO")
    yahoo["TYPO"] = FakeTicker({"trailingPegRatio": None})  # what Yahoo returns for an unknown symbol
    result = core.fundamentals.refresh_fundamentals()
    assert result["no_statements"] == ["TYPO"]
    assert _sql("SELECT COUNT(*) FROM profiles WHERE ticker = 'TYPO'")[0][0] == 0
