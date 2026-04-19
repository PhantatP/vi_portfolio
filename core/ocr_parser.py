# core/ocr_parser.py
import easyocr
import re
import datetime
import torch
import logging

# Set up logging for device info
logger = logging.getLogger(__name__)

# Lazy reader initialization
READER = None

# Thai Month Mapping - Expanded for OCR typos
THAI_MONTHS_MAP = {
    # Std
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
    # Typos
    "1.ค.": 1, "ม.n.": 1, ",ค.": 1, "1,ค.": 1, "ม,ค.": 1
}

TICKER_FIX_MAP = {
    "JEPO": "JEPQ",
    "JEP0": "JEPQ",
    "NFE": "NEE"  # Based on previous observation
}

def parse_thai_date(date_str):
    """
    Parses dates like:
      '28 ม.ค. 68'
      '28 1.ค. 68'
      '71,ค. 68' (7 ม.ค. 68)
    Returns 'YYYY-MM-DD'.
    """
    # Relaxed regex: Day (1-2 digits), Month (anything non-space), Year (2 digits)
    # Handles: "28 ม.ค.", "71,ค." (where comma connects them)
    # \W* allows non-word chars like comma, dot between digits and month
    match = re.search(r"(\d{1,2})[\s,\.]*([^\s\d]+)\s+(\d{2})", date_str)
    if not match:
        return None
    
    day_str, month_str, year_short = match.groups()
    
    # Clean Day (e.g. 71 -> 7)
    day = int(day_str)
    if day > 31:
        # Heuristic: 71 -> 7
        day = int(str(day)[0])
    
    # Normalize month
    month_str = month_str.replace(",", ".").replace("1", "ม").replace("n", "ค").replace(";", ":")
    
    # Try exact match first
    month = None
    for k, v in THAI_MONTHS_MAP.items():
        if k in month_str or month_str in k:
            month = v
            break
            
    # Hard fallback: if still None, try to just see if it contains "."
    if not month:
        if "ม" in month_str and "ค" in month_str: month = 1
        elif "ก" in month_str and "พ" in month_str: month = 2
        
    if not month:
        # One last try: '1.n.' -> Jan
        if '1' in month_str or 'n' in month_str: 
             month = 1
    
    if not month:
        return None
        
    # Year
    be_year = int(year_short)
    if be_year < 100:
        be_year += 2500
    ad_year = be_year - 543
    
    return f"{ad_year}-{month:02d}-{day:02d}"

def clean_number(s):
    s = s.replace(",", "").replace("o", "0").replace("O", "0")
    negative = s.strip().startswith("-")
    m = re.search(r"(\d+\.?\d*)", s)
    if m:
        val = float(m.group(1))
        return -val if negative else val
    return None

def get_reader():
    """
    Initializes or returns the easyocr Reader with appropriate GPU settings.
    """
    global READER
    if READER is None:
        use_gpu = torch.cuda.is_available()
        # You could also check for specific hardware if needed, 
        # but torch.cuda.is_available() is standard for easyocr/pytorch.
        logger.info(f"Initializing easyocr Reader (GPU={use_gpu})")
        READER = easyocr.Reader(['th', 'en'], gpu=use_gpu, verbose=False)
    return READER

def parse_dime_image(image_input):
    reader = get_reader()
    results = reader.readtext(image_input, detail=0)
    
    transactions = []
    current_tx = None
    
    for i, line in enumerate(results):
        line = line.strip()
        
        # 0. Skip Month Headers (e.g. "มกราคม 2569") — but NOT transaction lines
        # A header is: has Thai month key AND a 4-digit year AND no English ticker-like word
        if any(m in line for m in THAI_MONTHS_MAP.keys()) and re.search(r"\d{4}", line) and not re.search(r"[A-Z]{1,5}", line):
            continue

        # 1. Detect Header: "ซื้อ/ขาย/ปันผล/ภาษี TICKER"
        # Typos: ซื้อ, ซื่อ, ขื่อ, ขาย, ปันผล, ภาษี, ปืนผล
        # "ภาษีหัก ณ ที่จ่ายเงินปันผล MSFT" -> Type: Tax, Ticker: MSFT
        
        type_match = re.search(r"^(ซื้อ|ซื่อ|ขื่อ|ขาย|ปันผล|ปืนผล|ภาษี)", line)
        if type_match:
            raw_type = type_match.group(1)
            
            # Determine Side/Type
            if "ขาย" in raw_type: side = "sell"
            elif "ปันผล" in raw_type or "ปืนผล" in raw_type: side = "dividend"
            elif "ภาษี" in raw_type: side = "tax"
            else: side = "buy" # Default to buy for ซื้อ/ซื่อ/ขื่อ
            
            # Extract Ticker: everything after the type (and maybe 'หัก ...')
            # "ซื้อ AMZN" -> "AMZN"
            # "ภาษีหัก ณ ที่จ่ายเงินปันผล MSFT" -> "MSFT" relative to end?
            
            # Remove the detected type keyword first
            rem = line[len(raw_type):].strip()
            
            # Heuristic:
            # If "tax", ignore all the Thai text "หัก ณ ที่จ่าย..." and find the last English word?
            # If "dividend" or "buy/sell", usually just "TICKER"
            
            # Find all potential ticker parts (A-Z, digits, dot)
            # Filter out Thai characters
            
            # Split by space
            parts = rem.split()
            # Filter parts that look like tickers (mostly English/Numbers)
            potential_tickers = []
            for p in parts:
                p = p.strip()
                # 2-chars minimum usually? Or "V" is 1 char.
                if re.match(r"^[A-Za-z0-9\.]+$", p):
                    potential_tickers.append(p)
            
            ticker = "UNKNOWN"
            if potential_tickers:
                # Usually the ticker is the *last* english word in the line for things like "Dividend AAPL" 
                # or "Tax ... AAPL"
                # But for "Buy AAPL", it's the *first* (and only).
                # safely take the last one roughly works for all observed cases?
                # "ซื้อ AMZN" -> ["AMZN"] -> last is AMZN
                # "ภาษี... MSFT" -> ["MSFT"] -> last is MSFT
                ticker = potential_tickers[-1]
            
            # But "V." might be "V" with noise, or valid? usually noise.
            ticker = ticker.rstrip(".")
            
            # Apply auto-correction
            ticker = TICKER_FIX_MAP.get(ticker.upper(), ticker.upper())

            # Start new tx
            current_tx = {
                "ticker": ticker.upper(),
                "side": side,
                "raw_date": None,
                "trade_date": None,
                "quantity": None,
                "price": None,
                "price_currency": "USD" if not ticker.endswith(".BK") else "THB",
                "total_amount": None,
                "amount_currency": "THB" # Default
            }
            transactions.append(current_tx)
            
            # Header often has amount on the right.
            # But sometimes it's "0.01 USD" or "0.392 หุ้น"
            # Since line iteration here is linear, the 'right' text might be the NEXT item in results list.
            # We check the current line for amount? Usually OCR separates them.
            continue
        
        if not current_tx:
            continue
            
        # 2. Total Amount / Quantity in Header or Line 2
        # Patterns: 
        # "999.80 บาท" -> Amount, THB
        # "0.08 USD" -> Amount, USD
        # "0.3927357 หุ้น" -> Quantity (likely Sell header)
        
        # Check for currency
        if line.endswith("บาท"):
            val = clean_number(line)
            if val is not None:
                # Usually this is Total Amount
                if current_tx["total_amount"] is None:
                    current_tx["total_amount"] = val
                    current_tx["amount_currency"] = "THB"
            continue
            
        if line.endswith("USD") or line.endswith("usd"):
            val = clean_number(line)
            if val is not None:
                if current_tx["total_amount"] is None:
                    current_tx["total_amount"] = val
                    current_tx["amount_currency"] = "USD"
            continue
            
        if "หุ้น" in line or "หุ่น" in line or "หุน" in line: # 'Shares' + typo
            val = clean_number(line)
            if val is not None:
                 # If this appears, it's Quantity.
                 # Note: in "Sell", this might be the only place quantity appears?
                 # Or in "Buy", quantity appears in "จำนวนหุ้น" line.
                 # We prefer "จำนวนหุ้น" line if it exists, but this is a good fallback/primary for header.
                 current_tx["quantity"] = val
            continue
            
        # 3. Price: "ราคาที่ได้จริง"
        if "ราคา" in line or "ได้จริง" in line:
            val = clean_number(line)
            if val is not None:
                current_tx["price"] = val
            continue
            
        # 4. Explicit Quantity Line: "จำนวนหุ้น"
        if "จานวน" in line or "จำนวน" in line or "หัน" in line:
            # Need to avoid "หุ้น" matched in generic check above effectively?
            # Actually, overwriting is fine if valid.
            val = clean_number(line)
            if val is not None:
                current_tx["quantity"] = val
            continue

        # 5. Date: Pattern "\d ... \d"
        # "28 ม.ค. 68", "28 1.n. 68"
        # "13 ม.ค. 69"
        if re.search(r"^\d{1,2}.+\d{2}", line):
            # Check if it has time "น." to be sure OR just looks like a date?
            # Dime ALWAYS puts date.
            dt = parse_thai_date(line)
            if dt:
                current_tx["trade_date"] = dt
                current_tx["raw_date"] = line
            continue

    return transactions
