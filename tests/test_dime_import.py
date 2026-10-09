"""Dime PDF parsing + import. Fixtures mimic pypdf's text layout with made-up values."""
import io
import json
import sqlite3

import pytest
from pypdf import PdfWriter

import core.db
import core.db_init
import core.transactions
from core import dime_import
from core.dime_pdf import DimeParseError, parse_confirmation_note, parse_monthly_statement, read_pdf_text

NOTE = """--- page 1
Confirmation Note / Receipt / Tax Invoice
80000000000
2026091400000001
DIMEOS20260914000001
14/09/2026
11/09/2026
Settlement Date Transaction Type
100001 14/09/2026 SEL
AAPL
[XNAS]
2.0000000 200.00 USD 400.00 0.64
21.09
0.00
0.00
399.36
13,160.6213,181.71
100002 14/09/2026 BUY
VOO
[ARCX]
0.5000000 600.00 USD 300.00 0.48
15.82
0.00
0.00
300.48
9,902.199,886.37
1 / Page 2
--- page 2
Total Buy
9,902.19
13,160.62
0.00
0.00
0.00
11 กันยายน 2569
11 September 2026
32.9539
"""

REWARD_ROW = """100003 14/09/2026 REW
NVDA
[XNAS]
0.0100000 100.00 USD 1.00 0.00
0.00
0.00
0.00
1.00
32.9532.95
"""
NOTE_WITH_REWARD = NOTE.replace("1 / Page 2", REWARD_ROW + "1 / Page 2")

VOO_ROW = """0.5000000 600.00 USD 300.00 0.48
15.82
0.00
0.00
300.48
9,902.199,886.37"""

STATEMENT = """Offshore Securities Account Monthly Statement
520.00 USD
มูลค่าเงินลงทุนรวม / Total Balance
( ไม่รวมเงินปันผลตั้งแต่ลงทุน 12.34 USD ≈ 400.00 THB )
Cash Balance
100.50 USD
ข้อมูล ณ 30 กันยายน 2569 / As of 30 September 2026
 1 USD = 33.39 THB
หุ้นสามัญ / Common Stock
AAPL
Apple Inc.
40.00% 1.0000000 150.00 210.00 + 40.00% + 60.00 210.00
VOO
Vanguard S&P 500 ETF
60.00% 0.5000000 600.00 620.00 + 3.33% + 10.00 310.00
รวม 100.00% + 15.38% + 70.00 520.00
"""


def test_parse_confirmation_note():
    note = parse_confirmation_note(NOTE)
    assert note["note_no"] == "DIMEOS20260914000001"
    assert note["trade_date"] == "2026-09-11"  # effective date, not settlement
    assert note["errors"] == [] and note["skipped"] == []
    buy, sell = note["rows"]  # buys first
    assert sell == pytest.approx({**sell, "side": "sell", "ticker": "AAPL", "quantity": 2.0, "price": 200.0,
                                  "fee": 0.64, "usd_amount": 400.0, "thb_amount": 13181.71})
    assert sell["external_id"] == "DIMEOS20260914000001:100001"
    assert buy["side"] == "buy" and buy["total_thb"] == 9902.19 and buy["thb_amount"] == 9886.37
    assert buy["fx_thb_per_usd"] == pytest.approx(32.9546, abs=1e-4)


def test_unsupported_type_is_skipped():
    note = parse_confirmation_note(NOTE_WITH_REWARD)
    assert len(note["rows"]) == 2 and note["errors"] == []
    assert len(note["skipped"]) == 1 and "REW" in note["skipped"][0]


def test_cheap_stock_price_rounding_is_accepted():
    # 30 units averaging 27.0049 USD: printed price 27.00, gross 810.15
    cheap = "30.0000000 27.00 USD 810.15 0.48\n15.82\n0.00\n0.00\n810.63\n26,714.2426,698.42"
    text = NOTE.replace(VOO_ROW, cheap).replace("9,902.19\n13,160.62", "26,714.24\n13,160.62")
    note = parse_confirmation_note(text)
    assert note["errors"] == [] and len(note["rows"]) == 2


def test_confirmation_amounts_must_add_up():
    note = parse_confirmation_note(NOTE.replace("2.0000000 200.00", "3.0000000 200.00"))
    assert len(note["rows"]) == 1
    assert "do not add up" in note["errors"][0]


def test_swapped_thb_amounts_are_rejected():
    note = parse_confirmation_note(NOTE.replace("13,160.6213,181.71", "13,181.7113,160.62"))
    assert [r["ticker"] for r in note["rows"]] == ["VOO"]
    assert "THB amounts" in note["errors"][0]


def test_unrecognised_row_is_an_error_not_silently_dropped():
    note = parse_confirmation_note(NOTE.replace("[ARCX]", "ARCX"))
    assert [r["ticker"] for r in note["rows"]] == ["AAPL"]
    assert any("100002" in e for e in note["errors"])


def test_row_glued_to_previous_line_is_reported():
    note = parse_confirmation_note(NOTE.replace("13,181.71\n100002", "13,181.71 100002"))
    assert any("may be missing" in e for e in note["errors"])


def test_rows_must_sum_to_note_totals():
    note = parse_confirmation_note(NOTE.replace("9,902.19\n13,160.62", "9,902.19\n20,000.00"))
    assert any("note's total" in e for e in note["errors"])


def test_fx_date_may_differ_from_trade_date():
    # page 2's English date is the BOT FX date, e.g. Friday's rate for a Monday trade
    note = parse_confirmation_note(NOTE.replace("11 September 2026", "10 September 2026"))
    assert note["errors"] == [] and note["trade_date"] == "2026-09-11"


def test_issue_date_mistaken_for_trade_date_is_reported():
    note = parse_confirmation_note(NOTE.replace("11/09/2026\n", ""))  # only the issue date is left
    assert note["rows"] == [] and all("settlement" in e for e in note["errors"])


def test_rejects_other_documents():
    with pytest.raises(DimeParseError):
        parse_confirmation_note("some other pdf")
    with pytest.raises(DimeParseError):
        parse_monthly_statement("some other pdf")


def test_parse_monthly_statement():
    s = parse_monthly_statement(STATEMENT)
    assert s["as_of"] == "2026-09-30"
    assert (s["cash_usd"], s["dividends_since_start_usd"], s["fx_thb_per_usd"]) == (100.5, 12.34, 33.39)
    assert [(h["ticker"], h["shares"]) for h in s["holdings"]] == [("AAPL", 1.0), ("VOO", 0.5)]


def test_statement_missing_holding_is_rejected():
    with pytest.raises(DimeParseError, match="Total Balance"):
        parse_monthly_statement(STATEMENT.replace("VOO\nVanguard", "VOO Vanguard"))


def test_statement_unsigned_return_is_accepted():
    s = parse_monthly_statement(STATEMENT.replace("+ 3.33% + 10.00", "0.00% 0.00"))
    assert len(s["holdings"]) == 2


def test_wrong_pdf_password():
    w = PdfWriter()
    w.add_blank_page(100, 100)
    w.encrypt("right")
    buf = io.BytesIO()
    w.write(buf)
    assert read_pdf_text(buf.getvalue(), "right").strip() == ""
    with pytest.raises(DimeParseError):
        read_pdf_text(buf.getvalue(), "wrong")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(core.db, "DB_PATH", path)
    monkeypatch.setattr(core.db_init, "_import_schema_ready", False)
    monkeypatch.setattr(core.transactions, "detect_asset_profile", lambda t: {})
    monkeypatch.setattr(core.transactions, "fetch_usd_thb_rate", lambda: 33.0)
    core.db_init.init_db()
    return path


def _rows(path):
    con = sqlite3.connect(path)
    rows = con.execute("""SELECT a.ticker, t.side, t.trade_date, t.quantity, t.price, t.external_id
                          FROM transactions t JOIN assets a ON a.id = t.asset_id ORDER BY t.id""").fetchall()
    con.close()
    return rows


def test_import_is_idempotent(db):
    note = parse_confirmation_note(NOTE)
    first = dime_import.import_confirmation_note(note, dry_run=False, claimed=set())
    assert len(first["inserted"]) == 2
    second = dime_import.import_confirmation_note(note, dry_run=False, claimed=set())
    assert second["inserted"] == [] and len(second["existing"]) == 2
    assert len(_rows(db)) == 2


def test_dry_run_writes_nothing(db):
    res = dime_import.import_confirmation_note(parse_confirmation_note(NOTE), dry_run=True, claimed=set())
    assert len(res["inserted"]) == 2
    assert _rows(db) == []


def test_screenshot_row_is_corrected_not_duplicated(db):
    # typed from a screenshot: settlement date, 6-decimal qty, OCR-mangled price
    core.transactions.add_transaction(ticker="AAPL", broker="Dime", trade_date="2026-09-14", side="sell",
                                      quantity=1.999999, price_per_share=20.0, price_ccy="USD")
    res = dime_import.import_confirmation_note(parse_confirmation_note(NOTE), dry_run=False, claimed=set())
    assert len(res["corrected"]) == 1 and len(res["inserted"]) == 1
    rows = _rows(db)
    assert len(rows) == 2
    assert rows[0] == ("AAPL", "sell", "2026-09-11", 2.0, 200.0, "DIMEOS20260914000001:100001")


def test_screenshot_row_outside_window_is_not_matched(db):
    core.transactions.add_transaction(ticker="AAPL", broker="Dime", trade_date="2026-08-01", side="sell",
                                      quantity=2.0, price_per_share=200.0, price_ccy="USD")
    res = dime_import.import_confirmation_note(parse_confirmation_note(NOTE), dry_run=False, claimed=set())
    assert res["corrected"] == [] and len(res["inserted"]) == 2


def test_screenshot_row_with_wrong_date_matches_on_exact_qty_and_price(db):
    core.transactions.add_transaction(ticker="VOO", broker="Dime", trade_date="2025-01-03", side="buy",
                                      quantity=0.5000001, price_per_share=600.0, price_ccy="USD")
    text = NOTE.replace("0.5000000 600.00", "0.5000001 600.00")
    res = dime_import.import_confirmation_note(parse_confirmation_note(text), dry_run=False, claimed=set())
    assert len(res["corrected"]) == 1 and len(res["inserted"]) == 1  # AAPL inserted, VOO corrected
    assert ("VOO", "buy", "2026-09-11", 0.5000001, 600.0, "DIMEOS20260914000001:100002") in _rows(db)


def test_whole_share_qty_far_away_is_not_matched(db):
    core.transactions.add_transaction(ticker="AAPL", broker="Dime", trade_date="2025-01-03", side="sell",
                                      quantity=2.0, price_per_share=200.0, price_ccy="USD")
    res = dime_import.import_confirmation_note(parse_confirmation_note(NOTE), dry_run=False, claimed=set())
    assert res["corrected"] == []


def test_bad_file_does_not_stop_the_batch(db, monkeypatch):
    monkeypatch.setenv("VI_DIME_PDF_PASSWORD", "x")
    monkeypatch.setattr(dime_import, "read_pdf_text", lambda data, pw: data.decode())
    res = dime_import.import_files([
        ("Dime_offshore_confirmationNote_A.pdf", b"garbage"),
        ("Dime_offshore_confirmationNote_B.pdf", NOTE.encode()),
    ])
    assert [f["status"] for f in res["files"]] == ["error", "ok"]
    assert res["totals"]["inserted"] == 2
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM holdings").fetchone()[0] == 1  # VOO; AAPL sold down to 0
    con.close()


def test_reconcile(db):
    core.transactions.add_transaction(ticker="AAPL", broker="Dime", trade_date="2026-09-01", side="buy",
                                      quantity=1.0, price_per_share=150.0, price_ccy="USD")
    core.transactions.add_transaction(ticker="VOO", broker="Dime", trade_date="2026-10-02", side="buy",
                                      quantity=0.5, price_per_share=600.0, price_ccy="USD")  # after statement
    core.transactions.add_transaction(ticker="PTT.BK", broker="Dime", trade_date="2026-09-01", side="buy",
                                      quantity=100, price_per_share=35.0, price_ccy="THB")  # not offshore
    rec = dime_import.reconcile(parse_monthly_statement(STATEMENT))
    assert not rec["matches"]
    assert rec["mismatches"] == [{"ticker": "VOO", "dime_shares": 0.5, "db_shares": 0.0, "diff": 0.5}]


def _holding(path, ticker):
    con = sqlite3.connect(path)
    row = con.execute("""SELECT h.quantity, h.avg_price FROM holdings h JOIN assets a ON a.id = h.asset_id
                         WHERE a.ticker = ?""", (ticker,)).fetchone()
    con.close()
    return row


def test_statement_avg_cost_overrides_computed_cost(db):
    # Dime moved AAPL's avg cost to 150 after a partial sell; moving average would keep 125
    add = core.transactions.add_transaction
    add(ticker="AAPL", broker="Dime", trade_date="2026-08-01", side="buy", quantity=1.0,
        price_per_share=100.0, price_ccy="USD", thb_amount=3300.0)
    add(ticker="AAPL", broker="Dime", trade_date="2026-08-15", side="buy", quantity=1.0,
        price_per_share=150.0, price_ccy="USD", thb_amount=4950.0)
    add(ticker="AAPL", broker="Dime", trade_date="2026-09-11", side="sell", quantity=1.0,
        price_per_share=200.0, price_ccy="USD")
    dime_import._record_file("Dime_monthly_statement_x.pdf", "monthly_statement", "ok",
                             json.dumps(parse_monthly_statement(STATEMENT)))
    core.transactions.rebuild_holdings_from_transactions()
    qty, avg_thb = _holding(db, "AAPL")
    assert qty == pytest.approx(1.0) and avg_thb == pytest.approx(4125.0 * 150 / 125)

    # trades after the statement average on top of Dime's cost
    add(ticker="AAPL", broker="Dime", trade_date="2026-10-02", side="buy", quantity=1.0,
        price_per_share=250.0, price_ccy="USD", thb_amount=8250.0)
    core.transactions.rebuild_holdings_from_transactions()
    qty, avg_thb = _holding(db, "AAPL")
    assert qty == pytest.approx(2.0) and avg_thb == pytest.approx((4950.0 + 8250.0) / 2)


def test_statement_with_different_qty_is_not_used_as_anchor(db):
    # an unsettled trade means Dime's count differs; keep the computed cost
    core.transactions.add_transaction(ticker="VOO", broker="Dime", trade_date="2026-09-30", side="buy",
                                      quantity=0.7, price_per_share=500.0, price_ccy="USD", thb_amount=11550.0)
    dime_import._record_file("Dime_monthly_statement_x.pdf", "monthly_statement", "ok",
                             json.dumps(parse_monthly_statement(STATEMENT)))
    core.transactions.rebuild_holdings_from_transactions()
    assert _holding(db, "VOO")[1] == pytest.approx(11550.0 / 0.7)
