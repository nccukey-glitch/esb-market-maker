import os
import json
import re
import requests
from pathlib import Path
from typing import Dict, Optional

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

BROKER_CACHE_FILE = RAW_DATA_DIR / "brokers.json"
BROKER_XLS_FILE = RAW_DATA_DIR / "twse_broker_raw.xls"
LOCAL_BROKER_CACHE_FILE = LOCAL_DATA_DIR / "brokers.json"
LOCAL_BROKER_XLS_FILE = LOCAL_DATA_DIR / "twse_broker_raw.xls"

TWSE_BROKER_EXCEL_URL = "https://www.twse.com.tw/rwd/zh/brokerService/outPutExcel"
TWSE_BROKER_OPENAPI_URL = "https://openapi.twse.com.tw/v1/brokerService/brokerList"

# Base head-office names for resolving T-ending and general brokers
KNOWN_BROKERS = {
    "102": "合庫",
    "103": "土銀",
    "104": "臺銀",
    "111": "台企銀",
    "123": "彰銀",
    "126": "宏遠",
    "136": "麥格理",
    "144": "美林",
    "147": "台灣摩根士丹利",
    "148": "高盛",
    "156": "野村",
    "159": "花旗環球",
    "165": "瑞銀",
    "218": "亞東",
    "505": "大展",
    "511": "富隆",
    "526": "美好",
    "532": "高橋",
    "538": "第一金",
    "551": "大昌",
    "560": "國票",
    "585": "統一",
    "596": "石橋",
    "601": "新興",
    "611": "台中銀",
    "616": "中信",
    "646": "福勝",
    "648": "福邦",
    "662": "福勝",
    "691": "德信",
    "700": "兆豐",
    "703": "致和",
    "779": "國票",
    "838": "大昌",
    "845": "康和",
    "856": "新光",
    "884": "玉山",
    "888": "國泰",
    "910": "群益",
    "918": "群益",
    "920": "凱基",
    "930": "永昌",
    "960": "富邦",
    "980": "元大",
    "9A0": "永豐",
    "9B0": "台新",
}

class BrokerManager:
    """Manages broker codes, names, and branch mapping."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrokerManager, cls).__new__(cls)
            cls._instance._mapping = {}
            cls._instance._load_mapping()
        return cls._instance

    def _load_mapping(self):
        # 1. First load from cloud cache, then local cache
        for cfile in [BROKER_CACHE_FILE, LOCAL_BROKER_CACHE_FILE]:
            if cfile.exists():
                try:
                    with open(cfile, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if len(data) > 500:
                            self._mapping = data
                            return
                except Exception:
                    pass
        self._mapping = {}
        self.refresh_broker_list()

    def refresh_broker_list(self):
        """Fetches and parses broker branch list from official TWSE Excel file and OpenAPI."""
        # 1. Parse official TWSE Excel file if exists (cloud first, then local)
        xls_target = None
        if BROKER_XLS_FILE.exists():
            xls_target = BROKER_XLS_FILE
        elif LOCAL_BROKER_XLS_FILE.exists():
            xls_target = LOCAL_BROKER_XLS_FILE

        if xls_target:
            try:
                import xlrd
                wb = xlrd.open_workbook(str(xls_target))
                sheet = wb.sheet_by_index(0)
                for i in range(1, sheet.nrows):
                    row = sheet.row_values(i)
                    raw_code = str(row[0]).strip()
                    raw_name = str(row[1]).strip()
                    clean_name = re.sub(r'[\s\-]+', '', raw_name)
                    clean_name = clean_name.replace('綜合證券股份有限公司', '').replace('證券股份有限公司', '')
                    codes = raw_code.split('/')
                    for c in codes:
                        c = c.strip()
                        if c:
                            self._mapping[c] = clean_name
            except Exception as e:
                print(f"Warning: Failed to parse {xls_target}: {e}")

        # 2. Try TWSE OpenAPI for head offices
        try:
            resp = requests.get(TWSE_BROKER_OPENAPI_URL, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    code = item.get("Code", "").strip()
                    name = item.get("Name", "").strip()
                    if code and name and code not in self._mapping:
                        self._mapping[code] = name
        except Exception:
            pass

        # 3. Add base head offices and self-operated brokers
        for prefix, bname in KNOWN_BROKERS.items():
            t_code = f"{prefix}T"
            if t_code not in self._mapping:
                self._mapping[t_code] = f"{bname}自營"
            if prefix not in self._mapping:
                self._mapping[prefix] = bname
            if f"{prefix}0" not in self._mapping:
                self._mapping[f"{prefix}0"] = bname

        # 4. Explicit brokerage divisions and common codes
        explicit_mappings = {
            "9A95": "永豐金",
            "9A9H": "永豐金台南",
            "9A9h": "永豐金台南",
            "9B1g": "台新高雄",
            "989e": "元大中和",
            "6163": "中國信託永康",
            "9B2m": "台新成功",
            "9663": "富邦敦南",
            "526K": "大慶富順",
            "989P": "元大敦南",
            "9186": "群益新竹",
            "8882": "國泰台中",
            "7007": "兆豐竹北",
            "9897": "元大土城",
            "9B17": "台新營業部",
            "989X": "元大民生",
            "700G": "兆豐麻豆",
            "8888": "國泰敦南",
            "888A": "國泰館前",
            "9366": "永昌豐原",
            "9B11": "台新新營",
            "981q": "元大艋舺",
            "1040": "臺銀",
            "6160": "中國信託",
            "8560": "新光",
            "1260": "宏遠",
            "538L": "第一金經紀部",
            "9182": "群益經紀部",
            "9203": "凱基總公司",
            "9699": "富邦營業部",
            "9887": "元大經紀部",
            "616T": "中信自營",
            "648T": "福邦自營",
            "980T": "元大自營",
            "960T": "富邦自營",
            "538T": "第一金自營",
            "9A0T": "永豐自營",
            "700T": "兆豐自營",
            "9B0T": "台新自營",
            "910T": "群益自營",
            "930T": "永昌自營",
            "691T": "德信自營",
            "888T": "國泰自營",
            "126T": "宏遠自營",
            "920T": "凱基自營",
            "845T": "康和自營",
            "779T": "國票自營",
            "611T": "台中銀自營",
            "884T": "玉山自營",
            "585T": "統一自營",
            "102T": "合庫自營",
            "703T": "致和自營",
            "505T": "大展自營",
            "856T": "新光自營",
            "104T": "台銀自營",
        }
        self._mapping.update(explicit_mappings)

        # Save to Google Drive cloud storage (Primary)
        try:
            with open(BROKER_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Failed to write {BROKER_CACHE_FILE}: {e}")

        # Mirror save to local raw_data backup
        if RAW_DATA_DIR != LOCAL_DATA_DIR:
            try:
                with open(LOCAL_BROKER_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._mapping, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def get_name(self, broker_code: str) -> str:
        code = str(broker_code).strip()
        if code in self._mapping:
            return self._mapping[code]
        if code.upper() in self._mapping:
            return self._mapping[code.upper()]
        if code.lower() in self._mapping:
            return self._mapping[code.lower()]

        # Check if T ending (dealer)
        if code.endswith('T') or code.endswith('t'):
            prefix = code[:-1]
            if prefix in KNOWN_BROKERS:
                return f"{KNOWN_BROKERS[prefix]}自營"
            if prefix in self._mapping:
                return f"{self._mapping[prefix]}自營"
            return f"{code}自營"

        # Check 3-digit prefix
        if len(code) >= 3:
            prefix = code[:3]
            if prefix in KNOWN_BROKERS:
                return f"{KNOWN_BROKERS[prefix]}{code[3:]}"
            if f"{prefix}0" in self._mapping:
                return f"{self._mapping[f'{prefix}0']}{code[3:]}"

        return code

broker_manager = BrokerManager()

def get_broker_name(broker_code: str) -> str:
    return broker_manager.get_name(broker_code)
