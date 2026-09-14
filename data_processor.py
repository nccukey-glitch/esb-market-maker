from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

from data_fetcher.tpex import fetch_daily_raw, parse_daily_report, normalize_date
from calculation.chip import calculate_broker_chips
from calculation.pnl import calculate_stock_estimated_mm_pnl
from calculation.allocation import allocate_estimated_mm_pnl
from database.db_manager import db

def process_daily_market(trade_date: str, force_download: bool = False) -> Dict[str, Any]:
    """
    Downloads, parses, calculates, and stores analytics for all emerging stocks on a trade date.
    """
    api_date, file_date = normalize_date(trade_date)
    try:
        raw_json = fetch_daily_raw(trade_date, force_download=force_download)
    except Exception as e:
        return {
            "trade_date": file_date,
            "status": "error",
            "error": str(e),
            "stock_count": 0,
            "total_market_pnl": 0.0,
        }

    all_records = parse_daily_report(raw_json)

    if not all_records:
        return {
            "trade_date": file_date,
            "status": "no_data",
            "stock_count": 0,
            "total_market_pnl": 0.0,
        }

    # Group records by stock_id
    stocks_map = defaultdict(list)
    stock_names = {}
    for r in all_records:
        sid = r["stock_id"]
        stocks_map[sid].append(r)
        if sid not in stock_names and r["stock_name"]:
            stock_names[sid] = r["stock_name"]

    total_market_pnl = 0.0
    processed_count = 0

    for sid, records in stocks_map.items():
        sname = stock_names.get(sid, sid)

        # 1. Broker chips
        chip_records = calculate_broker_chips(records)

        # 2. Priced records & T records
        priced_records = [r for r in records if not r["is_t"] and r["price"] is not None]
        t_records = [r for r in records if r["is_t"]]

        # 3. Stock VWAP and Estimated MM PnL
        stock_pnl = calculate_stock_estimated_mm_pnl(priced_records)
        total_market_pnl += stock_pnl["total_estimated_mm_pnl"]

        # 4. MM allocations to ***T brokers
        allocations = allocate_estimated_mm_pnl(stock_pnl["total_estimated_mm_pnl"], t_records)

        # 5. Persist to DB
        db.save_daily_calculation(
            trade_date=file_date,
            stock_id=sid,
            stock_name=sname,
            chip_records=chip_records,
            stock_pnl=stock_pnl,
            allocations=allocations,
        )
        processed_count += 1

    return {
        "trade_date": file_date,
        "status": "ok",
        "stock_count": processed_count,
        "total_market_pnl": total_market_pnl,
    }

def process_date_range(start_date: str, end_date: str, force_download: bool = False) -> List[Dict[str, Any]]:
    """
    Processes all trading dates between start_date and end_date (inclusive).
    Skips weekends and checks if data already exists in database unless force_download is True.
    """
    _, start_norm = normalize_date(start_date)
    _, end_norm = normalize_date(end_date)

    dt_start = datetime.strptime(start_norm, "%Y%m%d")
    dt_end = datetime.strptime(end_norm, "%Y%m%d")

    if dt_start > dt_end:
        dt_start, dt_end = dt_end, dt_start

    available_dates = set(db.get_available_dates())
    results = []

    curr = dt_start
    while curr <= dt_end:
        # Skip Saturday (5) and Sunday (6)
        if curr.weekday() < 5:
            dt_str = curr.strftime("%Y%m%d")
            if dt_str in available_dates and not force_download:
                results.append({
                    "trade_date": dt_str,
                    "status": "already_cached",
                    "stock_count": 0,
                    "total_market_pnl": 0.0,
                })
            else:
                res = process_daily_market(dt_str, force_download=force_download)
                results.append(res)
        curr += timedelta(days=1)

    return results

