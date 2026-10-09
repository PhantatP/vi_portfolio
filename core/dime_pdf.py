# core/dime_pdf.py
"""
Parsers for Dime! (KKP Dime Securities) offshore PDFs:
  - Confirmation note  (Dime_offshore_confirmationNote_*.pdf): executed buy/sell orders
  - Monthly statement  (Dime_monthly_statement_*.pdf): holdings snapshot at month end

Parsers work on the text pypdf extracts, so they can be tested without the PDFs.
Every parsed row is cross-checked against its own totals; a row that does not add up
is reported as an error instead of being returned as data.
"""
import io
import re
from datetime import datetime

from pypdf import PdfReader

AMOUNT = r"\d{1,3}(?:,\d{3})*\.\d{2}"
NUM = r"[\d,]+(?:\.\d+)?"

SIDES = {"BUY": "buy", "SEL": "sell"}  # REW / EXC / EXP are reported as skipped

ROW_START = re.compile(r"^(\d+) (\d{2}/\d{2}/\d{4}) ([A-Z]{3})\s*$", re.M)
ROW = re.compile(
    rf"^(?P<order_id>\d+) (?P<settle>\d{{2}}/\d{{2}}/\d{{4}}) (?P<code>[A-Z]{{3}})\s*\n"
    rf"(?P<ticker>[A-Z][A-Z0-9.\-]*)\s*\n"
    rf"\[(?P<exchange>[A-Z]+)\]\s*\n"
    rf"(?P<units>{NUM}) (?P<price>{NUM}) (?P<ccy>[A-Z]{{3}}) (?P<gross>{NUM}) (?P<fee>{NUM})\s*\n"
    rf"(?P<fee_thb>{NUM})\s*\n(?P<wht>{NUM})\s*\n(?P<wht_thb>{NUM})\s*\n"
    rf"(?P<total>{NUM})\s*\n"
    rf"(?P<total_thb>{AMOUNT})(?P<gross_thb>{AMOUNT})\s*$",
    re.M,
)


class DimeParseError(ValueError):
    pass


def read_pdf_text(data: bytes, password: str | None) -> str:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(password or ""):
        raise DimeParseError("Wrong PDF password (set VI_DIME_PDF_PASSWORD)")
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _dmy(s: str) -> str:
    return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")


def parse_confirmation_note(text: str) -> dict:
    """
    Returns {"note_no", "trade_date", "rows": [...], "skipped": [...], "errors": [...]}.
    trade_date is the note's effective date (the earliest header date; the per-row
    date is the settlement date).
    """
    m = re.search(r"\b(DIMEOS\d+)\b", text)
    if not m:
        raise DimeParseError("Not a Dime offshore confirmation note (no DIMEOS number)")
    note_no = m.group(1)

    starts = list(ROW_START.finditer(text))
    if not starts:
        raise DimeParseError(f"{note_no}: no order rows found")
    header_dates = re.findall(r"^(\d{2}/\d{2}/\d{4})\s*$", text[: starts[0].start()], re.M)
    if not header_dates:
        raise DimeParseError(f"{note_no}: effective date not found")
    trade_date = min(_dmy(d) for d in header_dates)
    # (the English date on page 2 is the BOT FX rate date, which can be the previous business day)

    rows, skipped, errors = [], [], []
    exchanges = len(re.findall(r"^\[[A-Z]+\]\s*$", text, re.M))  # one per order row
    if exchanges != len(starts):
        errors.append(f"{note_no}: {exchanges} order rows but only {len(starts)} recognised; a row may be missing")
    matched = {m.start(): m for m in ROW.finditer(text)}
    for start in starts:
        order_id, code = start.group(1), start.group(3)
        m = matched.get(start.start())
        if m is None:
            errors.append(f"order {order_id}: row layout not recognised")
            continue
        if code not in SIDES:
            skipped.append(f"order {order_id}: {code} {m['ticker']} (unsupported type)")
            continue
        # US trades settle T+1; a gap outside 1-5 days means the wrong header date was taken as trade date
        settle_gap = (datetime.strptime(m["settle"], "%d/%m/%Y") - datetime.strptime(trade_date, "%Y-%m-%d")).days
        if not 1 <= settle_gap <= 5:
            errors.append(f"order {order_id}: settlement {m['settle']} is not 1-5 days after trade date {trade_date}")
            continue

        units, price, gross, fee, total = (_num(m[k]) for k in ("units", "price", "gross", "fee", "total"))
        gross_thb, total_thb, fee_thb = _num(m["gross_thb"]), _num(m["total_thb"]), _num(m["fee_thb"])
        side = SIDES[code]
        expected_total = gross + fee if side == "buy" else gross - fee
        # unit price is printed to 2 decimals, so units x price can be off by up to 0.005 per unit
        if abs(units * price - gross) > 0.005 * units + 0.01 or abs(expected_total - total) > 0.011:
            errors.append(f"order {order_id}: amounts do not add up ({units} x {price} vs {gross}, total {total})")
            continue
        fx = gross_thb / gross if gross else 0.0
        thb_tol = 0.005 * fx + 0.02  # USD amounts are rounded to cents before conversion
        if (abs(total_thb - total * fx) > thb_tol or abs(fee_thb - fee * fx) > thb_tol
                or (total_thb < gross_thb if side == "buy" else total_thb > gross_thb)):
            errors.append(f"order {order_id}: THB amounts do not add up (gross {gross_thb}, total {total_thb}, fee {fee_thb})")
            continue

        rows.append({
            "external_id": f"{note_no}:{order_id}",
            "ticker": m["ticker"],
            "side": side,
            "trade_date": trade_date,
            "settle_date": _dmy(m["settle"]),
            "quantity": units,
            "price": price,
            "price_ccy": m["ccy"],
            "fee": fee,                  # incl. VAT, before Dime's monthly fee discount
            "fee_thb": fee_thb,
            "usd_amount": gross,
            "thb_amount": gross_thb,     # gross in THB; fee is stored separately
            "fx_thb_per_usd": round(fx, 4) if gross else None,
            "total_thb": total_thb,
        })

    # Page 2 prints Total Buy, Total Sell, fee, WHT, VAT (THB) just above the Thai and English dates
    totals = re.search(rf"^({AMOUNT})\n({AMOUNT})\n{AMOUNT}\n{AMOUNT}\n{AMOUNT}\n\d{{1,2}} \S+ \d{{4}}\n\d{{1,2}} [A-Z][a-z]+ \d{{4}}\s*$",
                       text, re.M)
    if totals and not skipped and not errors:
        for side, printed in (("buy", totals.group(1)), ("sell", totals.group(2))):
            side_rows = [r["total_thb"] for r in rows if r["side"] == side]
            parsed_total = sum(side_rows)
            if abs(parsed_total - _num(printed)) > 0.005 * len(side_rows) + 0.011:  # each row rounded to satang
                errors.append(f"{note_no}: {side} rows sum to {parsed_total:,.2f} THB but the note's total is {printed}")

    # Order within a trade date is unknown; buys first so a same-day sell never floors at 0 on rebuild
    rows.sort(key=lambda r: r["side"] != "buy")
    return {"note_no": note_no, "trade_date": trade_date, "rows": rows, "skipped": skipped, "errors": errors}


HOLDING = re.compile(
    rf"^(?P<ticker>[A-Z][A-Z0-9.\-]*)\s*\n"
    rf"(?P<name>.+)\n"
    rf"(?P<alloc>{NUM})% (?P<shares>{NUM}) (?P<avg_cost>{NUM}) (?P<price>{NUM}) "
    rf"(?:[+-] )?{NUM}% (?:[+-] )?{NUM} (?P<market_value>{NUM})\s*$",
    re.M,
)


def parse_monthly_statement(text: str) -> dict:
    """Returns {"as_of", "fx_thb_per_usd", "cash_usd", "dividends_since_start_usd", "holdings": [...]}."""
    if "Offshore Securities Account Monthly Statement" not in text:
        raise DimeParseError("Not a Dime offshore monthly statement")
    m = re.search(r"As of (\d{1,2} [A-Za-z]+ \d{4})", text)
    if not m:
        raise DimeParseError("Statement date not found")
    as_of = datetime.strptime(m.group(1), "%d %B %Y").strftime("%Y-%m-%d")

    fx = re.search(rf"1 USD = ({NUM}) THB", text)
    cash = re.search(rf"Cash Balance\s*\n\s*({NUM}) USD", text)
    div = re.search(rf"ปันผล\D*?({NUM}) USD", text)

    holdings = [{
        "ticker": h["ticker"],
        "name": h["name"].strip(),
        "shares": _num(h["shares"]),
        "avg_cost_usd": _num(h["avg_cost"]),
        "price_usd": _num(h["price"]),
        "market_value_usd": _num(h["market_value"]),
    } for h in HOLDING.finditer(text)]
    if not holdings:
        raise DimeParseError(f"Statement {as_of}: no holdings rows recognised")
    total = re.search(rf"({NUM}) USD\s*\n[^\n]*Total Balance", text)
    parsed_total = sum(h["market_value_usd"] for h in holdings)
    if total and abs(parsed_total - _num(total.group(1))) > 0.02:
        raise DimeParseError(f"Statement {as_of}: holdings sum to {parsed_total:,.2f} USD but Total Balance "
                             f"is {total.group(1)} USD; a holding row was not recognised")

    return {
        "as_of": as_of,
        "fx_thb_per_usd": _num(fx.group(1)) if fx else None,
        "cash_usd": _num(cash.group(1)) if cash else None,
        "dividends_since_start_usd": _num(div.group(1)) if div else None,
        "holdings": holdings,
    }
