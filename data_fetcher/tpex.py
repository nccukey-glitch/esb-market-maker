import os
import json
import re
import requests
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CLOUD_DIR = Path("/Users/lilinsung/Library/CloudStorage/GoogleDrive-keynes3495@gmail.com/我的雲端硬碟/ESM_DATE")
LOCAL_DATA_DIR = BASE_DIR / "raw_data"

CONFIGURED_DIR = Path(os.environ.get("ESM_DATA_DIR", str(DEFAULT_CLOUD_DIR)))
if CONFIGURED_DIR.exists():
    RAW_DATA_DIR = CONFIGURED_DIR
else:
    RAW_DATA_DIR = LOCAL_DATA_DIR

try:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

try:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

TPEX_DSS004_URL = "https://www.tpex.org.tw/www/zh-tw/emerging/dss004"

def normalize_date(date_str: str) -> Tuple[str, str]:
    """
    Normalizes a date string into:
    - api_date: 'YYYY/MM/DD'
    - file_date: 'YYYYMMDD'
    """
    clean_date = re.sub(r'[^0-9]', '', date_str.strip())
    if len(clean_date) == 8:
        year, month, day = clean_date[:4], clean_date[4:6], clean_date[6:]
        return f"{year}/{month}/{day}", clean_date
    elif len(clean_date) == 7:
        # ROC year e.g. 1150909 -> 20260909
        roc_year = int(clean_date[:3])
        year = str(roc_year + 1911)
        month, day = clean_date[3:5], clean_date[5:]
        return f"{year}/{month}/{day}", f"{year}{month}{day}"
    else:
        raise ValueError(f"Invalid date format: {date_str}")

def clean_int(val: Any) -> int:
    """Parses integer from string with comma or hyphen."""
    if val is None:
        return 0
    s = str(val).strip().replace(',', '')
    if not s or s == '-':
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0

def clean_float(val: Any) -> Optional[float]:
    """Parses float price from string. Returns None if '-' or missing."""
    if val is None:
        return None
    s = str(val).strip().replace(',', '')
    if not s or s == '-':
        return None
    try:
        return float(s)
    except ValueError:
        return None

import time

_tpex_session = None

def get_tpex_session() -> requests.Session:
    global _tpex_session
    if _tpex_session is None:
        _tpex_session = requests.Session()
        _tpex_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.tpex.org.tw/zh-tw/emerging/trading/broker-trades.html",
            "X-Requested-With": "XMLHttpRequest",
        })
    return _tpex_session

def fetch_daily_raw(trade_date: str, force_download: bool = False) -> dict:
    """
    Fetches raw daily report JSON from TPEx or cloud/local cache.
    Primary storage is Google Drive (ESM_DATE), with local mirror backup.
    Includes 3-attempt retry with backoff for resilient connection handling.
    """
    api_date, file_date = normalize_date(trade_date)
    cache_file = RAW_DATA_DIR / f"dss004_{file_date}.json"
    local_cache_file = LOCAL_DATA_DIR / f"dss004_{file_date}.json"

    if not force_download:
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        if local_cache_file.exists():
            try:
                with open(local_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    params = {
        "date": api_date,
        "response": "json"
    }

    session = get_tpex_session()
    last_err = None
    data = None

    for attempt in range(3):
        try:
            resp = session.get(TPEX_DSS004_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"無法自櫃買中心取得 {api_date} 交易資料 (嘗試 3 次)：{last_err}")

    # Save to Google Drive cloud storage (Primary)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not write to {cache_file}: {e}")

    # Mirror save to local raw_data backup
    if RAW_DATA_DIR != LOCAL_DATA_DIR:
        try:
            with open(local_cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return data

def parse_daily_report(raw_json: dict) -> List[Dict[str, Any]]:
    """
    Parses TPEx dss004 raw JSON data rows into structured dicts.
    Fields from TPEx: ["證券代號", "證券名稱", "證券商代號", "成交價", "買進股數", "賣出股數"]
    """
    if not raw_json or "tables" not in raw_json or not raw_json["tables"]:
        return []

    table = raw_json["tables"][0]
    data_rows = table.get("data", [])
    if not data_rows:
        return []

    records = []
    for row in data_rows:
        if len(row) < 6:
            continue
        stock_id = str(row[0]).strip()
        stock_name = str(row[1]).strip()
        broker_code = str(row[2]).strip()
        price = clean_float(row[3])
        buy_qty = clean_int(row[4])
        sell_qty = clean_int(row[5])

        # A record is a T-record if broker_code ends with 'T' or price is None
        is_t = broker_code.endswith('T') or price is None

        records.append({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "broker_code": broker_code,
            "is_t": is_t,
            "price": price,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
        })

    return records

def split_stock_records(records: List[Dict[str, Any]], stock_id: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filters records for a specific stock_id and splits them into:
    (stock_name, priced_records, t_records)
    """
    stock_records = [r for r in records if r["stock_id"] == stock_id]
    stock_name = stock_records[0]["stock_name"] if stock_records else ""

    priced_records = [r for r in stock_records if not r["is_t"] and r["price"] is not None]
    t_records = [r for r in stock_records if r["is_t"]]

    return stock_name, priced_records, t_records
