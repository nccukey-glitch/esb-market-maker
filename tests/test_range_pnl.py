import unittest
from database.db_manager import db
from calculation.range_pnl import (
    calculate_single_stock_range_pnl_method1,
    calculate_single_stock_range_pnl_method2,
    calculate_dual_range_pnl,
)

class TestRangePnL(unittest.TestCase):

    def setUp(self):
        self.db = db

    def test_single_day_equivalence(self):
        """
        When date range is 1 single day, Method 1 (daily sum) MUST be exactly equal
        to Method 2 (range pooled formula).
        """
        stock_pnls = self.db.get_market_range_stock_pnls("20260909", "20260909")
        self.assertGreater(len(stock_pnls), 300)

        for s in stock_pnls:
            self.assertEqual(s["method1_matched_qty"], s["method2_matched_qty"], f"Mismatch for {s['stock_id']}")
            self.assertAlmostEqual(s["method1_pnl"], s["method2_pnl"], delta=0.01, msg=f"Mismatch PnL for {s['stock_id']}")
            self.assertAlmostEqual(s["pnl_diff"], 0.0, delta=0.01)

    def test_single_day_broker_equivalence(self):
        """
        When date range is 1 single day, dealers' Method 1 PnL MUST equal Method 2 PnL.
        """
        dealer_pnls = self.db.get_market_range_broker_pnls("20260909", "20260909")
        self.assertGreater(len(dealer_pnls), 0)

        for d in dealer_pnls:
            self.assertAlmostEqual(d["method1_pnl"], d["method2_pnl"], delta=0.01, msg=f"Mismatch dealer PnL for {d['broker_code']}")
            self.assertAlmostEqual(d["pnl_diff"], 0.0, delta=0.01)

    def test_multi_day_calculation(self):
        """
        Tests calculation over multiple days (20260828 to 20260909).
        Verifies both Method 1 and Method 2 execute cleanly without error.
        """
        available_dates = self.db.get_available_dates()
        self.assertIn("20260828", available_dates)
        self.assertIn("20260909", available_dates)

        stock_pnls = self.db.get_market_range_stock_pnls("20260828", "20260909")
        self.assertGreater(len(stock_pnls), 300)

        dealer_pnls = self.db.get_market_range_broker_pnls("20260828", "20260909")
        self.assertGreater(len(dealer_pnls), 0)

        stock_detail = self.db.get_stock_range_detail("20260828", "20260909", "7932")
        self.assertIn("method1", stock_detail)
        self.assertIn("method2", stock_detail)
        self.assertIn("dealers", stock_detail)
        self.assertGreater(len(stock_detail["daily_rows"]), 0)

    def test_synthetic_math_dual_methods(self):
        """
        Synthetic multi-day data test to verify mathematical differences between
        Daily Cumulative (Method 1) and Pooled Range Formula (Method 2).
        Day 1: Buy 100 @ 10, Sell 100 @ 12 -> M1 PnL = (10 * 0.9968 - 12) * 100 = -203.2
        Day 2: Buy 200 @ 15, Sell 100 @ 11 -> Matched 100, M1 PnL = (15 * 0.9968 - 11) * 100 = 395.2
        M1 Total PnL = -203.2 + 395.2 = 192.0

        M2:
        Total Buy = 300, Total Buy Amount = 100*10 + 200*15 = 4000, Buy VWAP = 13.333333
        Total Sell = 200, Total Sell Amount = 100*12 + 100*11 = 2300, Sell VWAP = 11.5
        Matched = min(300, 200) = 200
        M2 Total PnL = (13.333333 * 0.9968 - 11.5) * 200 = (13.290667 - 11.5) * 200 = 358.1333
        """
        mock_data = {
            "20260901": {
                "priced_records": [
                    {"buy_qty": 100, "sell_qty": 0, "price": 10.0},
                    {"buy_qty": 0, "sell_qty": 100, "price": 12.0},
                ],
                "t_records": [
                    {"broker_code": "9A95T", "broker_name": "永豐金", "buy_qty": 50, "sell_qty": 50}
                ]
            },
            "20260902": {
                "priced_records": [
                    {"buy_qty": 200, "sell_qty": 0, "price": 15.0},
                    {"buy_qty": 0, "sell_qty": 100, "price": 11.0},
                ],
                "t_records": [
                    {"broker_code": "9A95T", "broker_name": "永豐金", "buy_qty": 100, "sell_qty": 50}
                ]
            }
        }

        res = calculate_dual_range_pnl(mock_data)
        m1 = res["method1"]
        m2 = res["method2"]

        self.assertAlmostEqual(m1["total_estimated_mm_pnl"], 192.0, delta=0.01)
        self.assertAlmostEqual(m2["total_estimated_mm_pnl"], 358.133, delta=0.01)
        self.assertNotEqual(m1["total_estimated_mm_pnl"], m2["total_estimated_mm_pnl"])
        self.assertEqual(res["matched_diff"], 0)

if __name__ == "__main__":
    unittest.main()
