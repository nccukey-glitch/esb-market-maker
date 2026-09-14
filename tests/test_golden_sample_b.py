import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data_fetcher.tpex import fetch_daily_raw, parse_daily_report
from calculation.chip import calculate_broker_chips

class TestGoldenSampleB(unittest.TestCase):
    """
    Validation for Golden Sample B: 2026/08/28, 7932 昱鐳應材
    Defined in Specification Section 13 (recalculated with official trading date 2026/08/28).
    """
    @classmethod
    def setUpClass(cls):
        cls.trade_date = "2026-08-28"
        cls.raw_data = fetch_daily_raw(cls.trade_date)
        cls.records = parse_daily_report(cls.raw_data)
        cls.stock_7932_records = [r for r in cls.records if r["stock_id"] == "7932"]
        cls.chips = calculate_broker_chips(cls.stock_7932_records)
        cls.chip_dict = {c["broker_code"]: c for c in cls.chips}

    def test_broker_count(self):
        self.assertGreater(len(self.stock_7932_records), 1000)
        self.assertIn("9A95", self.chip_dict)
        self.assertIn("1260", self.chip_dict)

    def test_broker_9a95_yongfeng(self):
        b = self.chip_dict["9A95"]
        # 買進 623,960 股 (623張)
        self.assertEqual(b["buy_qty"], 623960)
        self.assertEqual(b["buy_qty"] // 1000, 623)
        # 買進均價 380.88
        self.assertAlmostEqual(b["buy_avg_price"], 380.88, places=2)

        # 賣出 18,919 股 (18張)
        self.assertEqual(b["sell_qty"], 18919)
        self.assertEqual(b["sell_qty"] // 1000, 18)
        # 賣出均價 358.87
        self.assertAlmostEqual(b["sell_avg_price"], 358.87, places=2)

        # 買超 605,041 股 (605張)
        self.assertEqual(b["net_qty"], 605041)
        self.assertEqual(b["net_qty"] // 1000, 605)

    def test_broker_1260_hongyuan(self):
        b = self.chip_dict["1260"]
        # 買進 518,503 股 (518張)
        self.assertEqual(b["buy_qty"], 518503)
        self.assertEqual(b["buy_qty"] // 1000, 518)
        # 買進均價 380.75
        self.assertAlmostEqual(b["buy_avg_price"], 380.75, places=2)

        # 賣出 0
        self.assertEqual(b["sell_qty"], 0)
        self.assertIsNone(b["sell_avg_price"])

        # 買超 518,503 股 (518張)
        self.assertEqual(b["net_qty"], 518503)
        self.assertEqual(b["net_qty"] // 1000, 518)

if __name__ == "__main__":
    unittest.main()
