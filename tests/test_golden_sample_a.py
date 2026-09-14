import unittest
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data_fetcher.tpex import fetch_daily_raw, parse_daily_report, split_stock_records
from calculation.pnl import calculate_stock_estimated_mm_pnl
from calculation.allocation import allocate_estimated_mm_pnl

class TestGoldenSampleA(unittest.TestCase):
    """
    Validation for Golden Sample A: 2026/09/09, 1260 富味鄉
    Defined in Specification Section 12.
    """
    @classmethod
    def setUpClass(cls):
        cls.trade_date = "2026-09-09"
        cls.raw_data = fetch_daily_raw(cls.trade_date)
        cls.records = parse_daily_report(cls.raw_data)
        cls.stock_name, cls.priced, cls.t_records = split_stock_records(cls.records, "1260")

    def test_stock_records_split(self):
        self.assertEqual(self.stock_name, "富味鄉")
        # 1260 has 28 records in total: 26 priced broker rows and 2 T rows (616T, 648T)
        self.assertEqual(len(self.priced), 26)
        self.assertEqual(len(self.t_records), 2)

    def test_priced_broker_vwap_and_pnl(self):
        pnl = calculate_stock_estimated_mm_pnl(self.priced)

        # 1. Customer Buy side
        self.assertEqual(pnl["customer_buy_qty"], 25232)
        self.assertAlmostEqual(pnl["customer_buy_amount"], 776909.75, places=1)
        self.assertAlmostEqual(pnl["customer_buy_avg"], 30.790653, places=5)

        # 2. Customer Sell side
        self.assertEqual(pnl["customer_sell_qty"], 24262)
        self.assertAlmostEqual(pnl["customer_sell_amount"], 734791.0, places=1)
        self.assertAlmostEqual(pnl["customer_sell_avg"], 30.285673, places=5)

        # 3. Matched Qty
        self.assertEqual(pnl["matched_qty"], 24262)

        # 4. Spread and PnL
        self.assertAlmostEqual(pnl["gross_spread_pnl"], 12251.82, places=2)
        self.assertAlmostEqual(pnl["transaction_cost"], 2390.54, places=2)
        self.assertAlmostEqual(pnl["total_estimated_mm_pnl"], 9861.28, places=2)

    def test_t_broker_allocation(self):
        pnl = calculate_stock_estimated_mm_pnl(self.priced)
        allocations = allocate_estimated_mm_pnl(pnl["total_estimated_mm_pnl"], self.t_records)

        alloc_dict = {a["broker_code"]: a for a in allocations}
        self.assertIn("616T", alloc_dict)
        self.assertIn("648T", alloc_dict)

        # 616T
        a_616 = alloc_dict["616T"]
        self.assertEqual(a_616["buy_qty"], 18262)
        self.assertEqual(a_616["sell_qty"], 19232)
        self.assertEqual(a_616["total_volume"], 37494)
        self.assertAlmostEqual(a_616["volume_share"], 37494 / 49494, places=5)
        self.assertAlmostEqual(a_616["allocated_pnl"], 7470.38, places=2)

        # 648T
        a_648 = alloc_dict["648T"]
        self.assertEqual(a_648["buy_qty"], 6000)
        self.assertEqual(a_648["sell_qty"], 6000)
        self.assertEqual(a_648["total_volume"], 12000)
        self.assertAlmostEqual(a_648["volume_share"], 12000 / 49494, places=5)
        self.assertAlmostEqual(a_648["allocated_pnl"], 2390.90, places=2)

        # Sum of allocations equals total PnL
        total_allocated = sum(a["allocated_pnl"] for a in allocations)
        self.assertAlmostEqual(total_allocated, pnl["total_estimated_mm_pnl"], places=2)

if __name__ == "__main__":
    unittest.main()
