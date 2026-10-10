"""Agent views (core/briefs.py) computed from a seeded DB; no network."""
import sqlite3
from datetime import date, timedelta

import pytest

import core.briefs
import core.db
import core.db_init
import core.portfolio


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core.db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(core.db_init, "_schema_ready", False)
    monkeypatch.setattr(core.portfolio, "_fetch_live_price", lambda t: pytest.fail(f"live fetch for {t}"))
    core.db_init.init_db()
    con = sqlite3.connect(core.db.DB_PATH)
    yield con
    con.close()


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _prices(con, ticker, points):
    con.executemany("INSERT INTO price_daily (ticker, date, close, source) VALUES (?, ?, ?, 't')",
                    [(ticker, d, c) for d, c in points])


def _profile(con, ticker, quote_type="EQUITY", currency="USD", reporting="USD"):
    con.execute("INSERT INTO profiles (ticker, quote_type, name, currency, financial_currency, source) "
                "VALUES (?, ?, ?, ?, ?, 't')", (ticker, quote_type, f"{ticker} Inc", currency, reporting))


def _quarters(con, ticker, rows):
    """rows: {period_end: {metric: value}} for quarterly statements."""
    con.executemany(
        "INSERT INTO financials (ticker, statement, period_type, period_end, metric, value, source) "
        "VALUES (?, 'income', 'quarterly', ?, ?, ?, 't')",
        [(ticker, p, m, v) for p, ms in rows.items() for m, v in ms.items()])


def _hold(con, ticker, qty, avg_thb):
    asset_id = con.execute("INSERT INTO assets (ticker) VALUES (?) RETURNING id", (ticker,)).fetchone()[0]
    con.execute("INSERT INTO holdings (asset_id, broker, quantity, avg_price, currency) VALUES (?, 'Dime', ?, ?, 'THB')",
                (asset_id, qty, avg_thb))


QUARTERS = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]


def test_ttm_valuation_uses_normalized_income(db):
    _profile(db, "ABC")
    _prices(db, "ABC", [(_days_ago(1), 100.0)])
    _quarters(db, "ABC", {q: {"TotalRevenue": 250.0, "NetIncome": 50.0, "NormalizedIncome": 25.0,
                              "TotalUnusualItems": 25.0} for q in QUARTERS})
    db.execute("INSERT INTO financials VALUES ('ABC', 'balance', 'quarterly', '2026-06-30', "
               "'OrdinarySharesNumber', 10.0, 't', CURRENT_TIMESTAMP)")
    db.execute("INSERT INTO financials VALUES ('ABC', 'balance', 'quarterly', '2026-06-30', "
               "'StockholdersEquity', 500.0, 't', CURRENT_TIMESTAMP)")
    db.commit()

    f = core.briefs.ticker_brief("abc")["fundamentals"]

    assert f["basis"] == "ttm to 2026-06-30" and f["earnings_basis"] == "normalized"
    # market cap 100 * 10 = 1000; TTM normalized income 100, reported 200
    assert f["valuation"]["pe"] == 10.0 and f["valuation"]["pe_reported"] == 5.0
    assert f["valuation"]["pb"] == 2.0 and f["valuation"]["ps"] == 1.0
    assert f["quality"]["net_margin_pct"] == 10.0 and f["quality"]["roe_pct"] == 20.0


def test_gap_in_quarters_falls_back_to_fiscal_year(db):
    _profile(db, "ABC")
    _quarters(db, "ABC", {q: {"TotalRevenue": 1.0} for q in ["2024-06-30", "2025-12-31", "2026-03-31", "2026-06-30"]})
    db.execute("INSERT INTO financials VALUES ('ABC', 'income', 'annual', '2025-12-31', 'TotalRevenue', 9.0, 't', "
               "CURRENT_TIMESTAMP)")
    db.commit()
    assert core.briefs.ticker_brief("ABC")["fundamentals"]["basis"] == "fy 2025-12-31"


def test_valuation_skipped_when_currencies_differ(db):
    _profile(db, "TM", currency="USD", reporting="JPY")
    _prices(db, "TM", [(_days_ago(1), 180.0)])
    _quarters(db, "TM", {q: {"TotalRevenue": 1e12, "NetIncome": 1e11} for q in QUARTERS})
    db.commit()
    b = core.briefs.ticker_brief("TM")
    assert b["reporting_currency"] == "JPY"
    assert b["fundamentals"]["valuation"] == {"skipped": "price is in USD, statements in JPY"}
    assert b["fundamentals"]["quality"]["net_margin_pct"] == 10.0  # ratios within statements still work


def test_price_stats_and_position(db):
    _prices(db, "VOO", [(_days_ago(400), 400.0), (_days_ago(200), 550.0), (_days_ago(40), 450.0),
                        (_days_ago(1), 500.0)])
    _prices(db, "USDTHB=X", [(_days_ago(1), 30.0)])
    db.execute("INSERT INTO corporate_actions VALUES ('VOO', ?, 'dividend', 5.0, 't', CURRENT_TIMESTAMP)",
               (_days_ago(100),))
    _hold(db, "VOO", 2, 12000.0)
    db.commit()

    b = core.briefs.ticker_brief("VOO")

    p = b["price"]
    # each window uses the last close on or before its start: 3m -> the 200-days-ago close
    assert p["return_pct"] == {"1m": 11.1, "3m": -9.1, "1y": 25.0}  # no data 3y/5y back
    assert p["high_52w"] == 550.0 and p["from_52w_high_pct"] == -9.1
    assert p["dividend_yield_ttm_pct"] == 1.0
    assert b["position"] == {"quantity": 2.0, "value_thb": 30000.0, "cost_thb": 24000.0,
                             "pl_pct": 25.0, "weight_pct": 100.0}
    assert "fundamentals" not in b and "notes" not in b  # empty sections are omitted


def test_never_calls_yahoo_even_when_stored_data_is_stale_or_missing(db, monkeypatch):
    import core.fx
    monkeypatch.setattr(core.fx.yf, "Ticker", lambda t: pytest.fail("live FX fetch"))
    _prices(db, "USDTHB=X", [(_days_ago(60), 31.0)])  # stale: live mode would go to Yahoo
    _prices(db, "VOO", [(_days_ago(1), 500.0)])
    _hold(db, "VOO", 1, 10000.0)
    _hold(db, "NEWCO", 1, 5000.0)                       # no stored price at all
    db.commit()

    s = core.briefs.portfolio_summary()

    assert s["usd_thb"]["rate"] == 31.0  # the stale stored rate the totals were built with
    assert s["total_value_thb"] == 15500.0
    assert s["positions_missing_price"] == ["NEWCO"]
    newco = next(p for p in s["positions"] if p["ticker"] == "NEWCO")
    assert newco == {"ticker": "NEWCO", "price_missing": True}  # not a -100% loss
    assert s["unrealized_pl_pct"] == 55.0  # 15500 vs 10000, NEWCO's cost excluded
    assert core.briefs.ticker_brief("NEWCO")["position"]["price_missing"] is True


def test_balance_items_fall_back_to_latest_period_that_has_them(db):
    _profile(db, "PTT.BK", currency="THB", reporting="THB")
    _prices(db, "PTT.BK", [(_days_ago(1), 30.0)])
    _quarters(db, "PTT.BK", {q: {"TotalRevenue": 100.0, "NetIncome": 10.0} for q in QUARTERS})
    db.execute("INSERT INTO financials VALUES ('PTT.BK', 'balance', 'annual', '2025-12-31', "
               "'OrdinarySharesNumber', 4.0, 't', CURRENT_TIMESTAMP)")  # latest quarter has no share count
    db.commit()
    assert core.briefs.ticker_brief("PTT.BK")["fundamentals"]["valuation"]["pe"] == 3.0  # 30*4 / 40


def test_growth_skips_a_negative_base_and_is_labelled(db):
    db.executemany("INSERT INTO financials VALUES ('ABC', 'income', 'annual', ?, 'TotalRevenue', ?, 't', "
                   "CURRENT_TIMESTAMP)", [("2024-12-31", -5.0), ("2025-12-31", 10.0)])
    db.commit()
    g = core.briefs.ticker_brief("ABC")["fundamentals"]["growth_pct"]
    assert g == {"basis": "fy 2025-12-31 vs 2024-12-31"}  # no sign-flipped revenue_yoy


def test_untracked_ticker_has_no_brief(db):
    assert core.briefs.ticker_brief("NOPE") is None


def test_portfolio_allocation_against_targets(db):
    _prices(db, "USDTHB=X", [(_days_ago(1), 30.0)])
    for t, px, country, tags in [("AAPL", 100.0, "United States", "growth"), ("CPALL.BK", 60.0, None, "dividend"),
                                 ("VGK", 50.0, None, None)]:
        _prices(db, t, [(_days_ago(1), px)])
        _hold(db, t, 1, 1.0)
        db.execute("UPDATE assets SET country = ?, tags = ? WHERE ticker = ?", (country, tags, t))
    db.commit()

    a = core.briefs.portfolio_summary()["allocation_pct"]

    # values in THB: AAPL 3000, CPALL 60, VGK 1500 -> total 4560
    assert a["country"] == {"US": 65.8, "UNKNOWN": 32.9, "TH": 1.3}
    assert a["style"] == {"growth": 65.8, "untagged": 32.9, "dividend": 1.3}
    assert a["country_target"] == {"US": 40.0, "TH": 30.0, "OTHER": 30.0}


def test_price_history_takes_last_close_of_each_month(db):
    _prices(db, "VOO", [("2026-01-05", 1.0), ("2026-01-30", 2.0), ("2026-02-02", 3.0), ("2026-02-27", 4.0)])
    db.commit()
    h = core.briefs.price_history("VOO", start="2026-01-01", end="2026-03-01", interval="monthly")
    assert h["points"] == [["2026-01-30", 2.0], ["2026-02-27", 4.0]]


def test_financials_table_scales_and_reports_unknowns(db):
    _quarters(db, "ABC", {"2026-06-30": {"TotalRevenue": 2.5e9, "DilutedEPS": 1.23}})
    db.commit()
    t = core.briefs.financials_table("ABC", "quarterly", metrics=["TotalRevenue", "DilutedEPS", "Nope"])
    assert t["metrics"] == {"TotalRevenue": [2500.0], "DilutedEPS": [1.23]}
    assert t["unknown_metrics"] == ["Nope"]


def test_data_status_flags_stale_prices(db):
    _prices(db, "USDTHB=X", [(_days_ago(30), 30.0)])
    db.execute("INSERT INTO job_runs (job, status, detail) VALUES ('prices_refresh', 'ok', '{\"missing\": [\"^SET.BK\"]}')")
    db.commit()
    s = core.briefs.data_status()
    assert s["jobs"]["prices_refresh"]["problems"] == {"missing": ["^SET.BK"]}
    assert "USDTHB=X" in s["prices_stale_or_missing"] and "^GSPC" in s["prices_stale_or_missing"]
