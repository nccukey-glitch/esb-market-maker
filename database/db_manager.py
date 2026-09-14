import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "esb.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

class DBManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Executes schema.sql if tables do not exist and applies schema migrations."""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            try:
                conn.execute("ALTER TABLE daily_broker_trades ADD COLUMN buy_ratio REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE daily_broker_trades ADD COLUMN sell_ratio REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass

    def save_stock(self, stock_id: str, stock_name: str):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO stock_master (stock_id, stock_name)
                VALUES (?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (stock_id, stock_name)
            )

    def save_daily_calculation(
        self,
        trade_date: str,
        stock_id: str,
        stock_name: str,
        chip_records: List[Dict[str, Any]],
        stock_pnl: Dict[str, Any],
        allocations: List[Dict[str, Any]],
    ):
        """Persists all calculations for a single stock on a specific trade_date."""
        with self.get_connection() as conn:
            # 1. Update stock master
            conn.execute(
                """
                INSERT INTO stock_master (stock_id, stock_name)
                VALUES (?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET stock_name=excluded.stock_name
                """,
                (stock_id, stock_name)
            )

            # 2. Save daily stock pnl
            conn.execute(
                """
                INSERT INTO daily_stock_pnl (
                    trade_date, stock_id, stock_name,
                    buy_qty, buy_amount, buy_vwap,
                    sell_qty, sell_amount, sell_vwap,
                    matched_qty, gross_spread_pnl, transaction_cost, total_estimated_mm_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, stock_id) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    buy_qty=excluded.buy_qty,
                    buy_amount=excluded.buy_amount,
                    buy_vwap=excluded.buy_vwap,
                    sell_qty=excluded.sell_qty,
                    sell_amount=excluded.sell_amount,
                    sell_vwap=excluded.sell_vwap,
                    matched_qty=excluded.matched_qty,
                    gross_spread_pnl=excluded.gross_spread_pnl,
                    transaction_cost=excluded.transaction_cost,
                    total_estimated_mm_pnl=excluded.total_estimated_mm_pnl
                """,
                (
                    trade_date, stock_id, stock_name,
                    stock_pnl["customer_buy_qty"], stock_pnl["customer_buy_amount"], stock_pnl["customer_buy_avg"],
                    stock_pnl["customer_sell_qty"], stock_pnl["customer_sell_amount"], stock_pnl["customer_sell_avg"],
                    stock_pnl["matched_qty"], stock_pnl["gross_spread_pnl"], stock_pnl["transaction_cost"], stock_pnl["total_estimated_mm_pnl"]
                )
            )

            # 3. Save broker chip trades
            for r in chip_records:
                conn.execute(
                    """
                    INSERT INTO daily_broker_trades (
                        trade_date, stock_id, broker_code, broker_name, is_t,
                        buy_qty, buy_amount, buy_avg_price, buy_ratio,
                        sell_qty, sell_amount, sell_avg_price, sell_ratio, net_qty
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trade_date, stock_id, broker_code) DO UPDATE SET
                        broker_name=excluded.broker_name,
                        is_t=excluded.is_t,
                        buy_qty=excluded.buy_qty,
                        buy_amount=excluded.buy_amount,
                        buy_avg_price=excluded.buy_avg_price,
                        buy_ratio=excluded.buy_ratio,
                        sell_qty=excluded.sell_qty,
                        sell_amount=excluded.sell_amount,
                        sell_avg_price=excluded.sell_avg_price,
                        sell_ratio=excluded.sell_ratio,
                        net_qty=excluded.net_qty
                    """,
                    (
                        trade_date, stock_id, r["broker_code"], r.get("broker_name", ""),
                        1 if r["is_t"] else 0,
                        r["buy_qty"], r["buy_amount"], r["buy_avg_price"], r.get("buy_ratio", 0.0),
                        r["sell_qty"], r["sell_amount"], r["sell_avg_price"], r.get("sell_ratio", 0.0), r["net_qty"]
                    )
                )

            # 4. Save MM allocations
            for a in allocations:
                conn.execute(
                    """
                    INSERT INTO daily_mm_allocation (
                        trade_date, stock_id, broker_code, broker_name,
                        buy_qty, sell_qty, total_volume, volume_share, allocated_pnl
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trade_date, stock_id, broker_code) DO UPDATE SET
                        broker_name=excluded.broker_name,
                        buy_qty=excluded.buy_qty,
                        sell_qty=excluded.sell_qty,
                        total_volume=excluded.total_volume,
                        volume_share=excluded.volume_share,
                        allocated_pnl=excluded.allocated_pnl
                    """,
                    (
                        trade_date, stock_id, a["broker_code"], a.get("broker_name", ""),
                        a["buy_qty"], a["sell_qty"], a["total_volume"], a["volume_share"], a["allocated_pnl"]
                    )
                )

    def get_market_stock_pnls(self, trade_date: str) -> List[Dict[str, Any]]:
        """Returns all stock estimated MM PnL rankings on a trade_date."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM daily_stock_pnl
                WHERE trade_date = ?
                ORDER BY total_estimated_mm_pnl DESC
                """,
                (trade_date,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_market_broker_pnls(self, trade_date: str) -> List[Dict[str, Any]]:
        """Returns sum of estimated MM PnL grouped by dealer broker on a trade_date."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    broker_code,
                    broker_name,
                    SUM(total_volume) as total_volume,
                    SUM(allocated_pnl) as total_pnl
                FROM daily_mm_allocation
                WHERE trade_date = ?
                GROUP BY broker_code
                ORDER BY total_pnl DESC
                """,
                (trade_date,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_stock_chip_records(self, trade_date: str, stock_id: str) -> List[Dict[str, Any]]:
        """Returns all broker chip records for a stock on a date."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM daily_broker_trades
                WHERE trade_date = ? AND stock_id = ?
                ORDER BY ABS(net_qty) DESC
                """,
                (trade_date, stock_id)
            )
            rows = [dict(row) for row in cur.fetchall()]
            total_buy = sum(r.get("buy_qty", 0) for r in rows)
            total_sell = sum(r.get("sell_qty", 0) for r in rows)
            for r in rows:
                if not r.get("buy_ratio"):
                    r["buy_ratio"] = (r.get("buy_qty", 0) / total_buy) if total_buy > 0 else 0.0
                if not r.get("sell_ratio"):
                    r["sell_ratio"] = (r.get("sell_qty", 0) / total_sell) if total_sell > 0 else 0.0
            return rows

    def get_stock_allocations(self, trade_date: str, stock_id: str) -> List[Dict[str, Any]]:
        """Returns all T-broker allocations for a stock on a date."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM daily_mm_allocation
                WHERE trade_date = ? AND stock_id = ?
                ORDER BY total_volume DESC
                """,
                (trade_date, stock_id)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_available_dates(self) -> List[str]:
        """Returns list of distinct trade dates available in daily_stock_pnl."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT DISTINCT trade_date FROM daily_stock_pnl ORDER BY trade_date ASC")
            return [row["trade_date"] for row in cur.fetchall()]

    def get_market_range_stock_pnls(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Returns all stocks in date range [start_date, end_date] with:
        - Method 1 PnL: Sum of daily total_estimated_mm_pnl
        - Method 2 PnL: Range pooled formula PnL
        - Difference: Method 2 - Method 1
        """
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    stock_id,
                    stock_name,
                    COUNT(DISTINCT trade_date) as trading_days,
                    SUM(buy_qty) as total_buy_qty,
                    SUM(buy_amount) as total_buy_amount,
                    SUM(sell_qty) as total_sell_qty,
                    SUM(sell_amount) as total_sell_amount,
                    SUM(matched_qty) as m1_matched_qty,
                    SUM(gross_spread_pnl) as m1_gross_spread_pnl,
                    SUM(transaction_cost) as m1_transaction_cost,
                    SUM(total_estimated_mm_pnl) as m1_pnl
                FROM daily_stock_pnl
                WHERE trade_date >= ? AND trade_date <= ?
                GROUP BY stock_id
                """,
                (start_date, end_date)
            )
            rows = [dict(r) for r in cur.fetchall()]

            results = []
            for r in rows:
                b_qty = r["total_buy_qty"]
                b_amt = r["total_buy_amount"]
                s_qty = r["total_sell_qty"]
                s_amt = r["total_sell_amount"]

                b_vwap = (b_amt / b_qty) if b_qty > 0 else 0.0
                s_vwap = (s_amt / s_qty) if s_qty > 0 else 0.0
                m2_matched = min(b_qty, s_qty)

                if m2_matched > 0 and b_qty > 0 and s_qty > 0:
                    m2_gross = (b_vwap - s_vwap) * m2_matched
                    m2_cost = b_vwap * 0.0032 * m2_matched
                    m2_pnl = (b_vwap * 0.9968 - s_vwap) * m2_matched
                else:
                    m2_gross = 0.0
                    m2_cost = 0.0
                    m2_pnl = 0.0

                m1_pnl = r["m1_pnl"]
                results.append({
                    "stock_id": r["stock_id"],
                    "stock_name": r["stock_name"],
                    "trading_days": r["trading_days"],
                    "range_buy_qty": b_qty,
                    "range_buy_vwap": b_vwap,
                    "range_sell_qty": s_qty,
                    "range_sell_vwap": s_vwap,
                    "method1_matched_qty": r["m1_matched_qty"],
                    "method1_pnl": m1_pnl,
                    "method2_matched_qty": m2_matched,
                    "method2_gross_spread": m2_gross,
                    "method2_cost": m2_cost,
                    "method2_pnl": m2_pnl,
                    "pnl_diff": m2_pnl - m1_pnl
                })

            results.sort(key=lambda x: x["method1_pnl"], reverse=True)
            return results

    def get_market_range_broker_pnls(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Calculates all dealers' range PnL under both Method 1 (sum of daily allocations)
        and Method 2 (range volume share of Method 2 stock PnL).
        """
        stock_pnls = self.get_market_range_stock_pnls(start_date, end_date)
        stock_m2_map = {s["stock_id"]: s["method2_pnl"] for s in stock_pnls}

        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT stock_id, SUM(total_volume) as stock_total_dealer_vol
                FROM daily_mm_allocation
                WHERE trade_date >= ? AND trade_date <= ?
                GROUP BY stock_id
                """,
                (start_date, end_date)
            )
            stock_dealer_totals = {r["stock_id"]: r["stock_total_dealer_vol"] for r in cur.fetchall()}

            cur = conn.execute(
                """
                SELECT
                    broker_code,
                    broker_name,
                    stock_id,
                    SUM(buy_qty) as total_buy,
                    SUM(sell_qty) as total_sell,
                    SUM(total_volume) as total_vol,
                    SUM(allocated_pnl) as m1_pnl
                FROM daily_mm_allocation
                WHERE trade_date >= ? AND trade_date <= ?
                GROUP BY broker_code, stock_id
                """,
                (start_date, end_date)
            )
            dealer_stock_rows = [dict(r) for r in cur.fetchall()]

            dealers = {}
            for r in dealer_stock_rows:
                bcode = r["broker_code"]
                bname = r["broker_name"]
                sid = r["stock_id"]
                vol = r["total_vol"]
                m1_pnl = r["m1_pnl"]

                tot_vol = stock_dealer_totals.get(sid, 0)
                s_m2_pnl = stock_m2_map.get(sid, 0.0)
                m2_pnl = (s_m2_pnl * (vol / tot_vol)) if tot_vol > 0 else 0.0

                if bcode not in dealers:
                    dealers[bcode] = {
                        "broker_code": bcode,
                        "broker_name": bname,
                        "total_volume": 0,
                        "method1_pnl": 0.0,
                        "method2_pnl": 0.0,
                    }
                dealers[bcode]["total_volume"] += vol
                dealers[bcode]["method1_pnl"] += m1_pnl
                dealers[bcode]["method2_pnl"] += m2_pnl

            results = []
            for bcode, d in dealers.items():
                d["pnl_diff"] = d["method2_pnl"] - d["method1_pnl"]
                results.append(d)
            results.sort(key=lambda x: x["method1_pnl"], reverse=True)
            return results

    def get_stock_range_chips(self, start_date: str, end_date: str, stock_id: str) -> List[Dict[str, Any]]:
        """Aggregates all broker chip trades for a stock in a date range."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    broker_code,
                    broker_name,
                    is_t,
                    SUM(buy_qty) as buy_qty,
                    SUM(buy_amount) as buy_amount,
                    SUM(sell_qty) as sell_qty,
                    SUM(sell_amount) as sell_amount,
                    SUM(net_qty) as net_qty
                FROM daily_broker_trades
                WHERE trade_date >= ? AND trade_date <= ? AND stock_id = ?
                GROUP BY broker_code
                ORDER BY ABS(SUM(net_qty)) DESC
                """,
                (start_date, end_date, stock_id)
            )
            rows = [dict(r) for r in cur.fetchall()]

            tot_buy = sum(r["buy_qty"] for r in rows)
            tot_sell = sum(r["sell_qty"] for r in rows)
            for r in rows:
                r["buy_avg_price"] = (r["buy_amount"] / r["buy_qty"]) if (r["buy_qty"] > 0 and not r["is_t"]) else None
                r["sell_avg_price"] = (r["sell_amount"] / r["sell_qty"]) if (r["sell_qty"] > 0 and not r["is_t"]) else None
                r["buy_ratio"] = (r["buy_qty"] / tot_buy) if tot_buy > 0 else 0.0
                r["sell_ratio"] = (r["sell_qty"] / tot_sell) if tot_sell > 0 else 0.0
            return rows

    def get_stock_range_detail(self, start_date: str, end_date: str, stock_id: str) -> Dict[str, Any]:
        """Returns multi-day breakdown and comparative Method 1 & 2 analytics for a single stock."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM daily_stock_pnl
                WHERE trade_date >= ? AND trade_date <= ? AND stock_id = ?
                ORDER BY trade_date ASC
                """,
                (start_date, end_date, stock_id)
            )
            daily_rows = [dict(r) for r in cur.fetchall()]

            cur = conn.execute(
                """
                SELECT * FROM daily_mm_allocation
                WHERE trade_date >= ? AND trade_date <= ? AND stock_id = ?
                ORDER BY trade_date ASC, total_volume DESC
                """,
                (start_date, end_date, stock_id)
            )
            alloc_rows = [dict(r) for r in cur.fetchall()]

            # Method 1
            m1_matched = sum(r["matched_qty"] for r in daily_rows)
            m1_gross = sum(r["gross_spread_pnl"] for r in daily_rows)
            m1_cost = sum(r["transaction_cost"] for r in daily_rows)
            m1_pnl = sum(r["total_estimated_mm_pnl"] for r in daily_rows)

            # Method 2
            tot_b_qty = sum(r["buy_qty"] for r in daily_rows)
            tot_b_amt = sum(r["buy_amount"] for r in daily_rows)
            tot_s_qty = sum(r["sell_qty"] for r in daily_rows)
            tot_s_amt = sum(r["sell_amount"] for r in daily_rows)

            m2_b_vwap = (tot_b_amt / tot_b_qty) if tot_b_qty > 0 else 0.0
            m2_s_vwap = (tot_s_amt / tot_s_qty) if tot_s_qty > 0 else 0.0
            m2_matched = min(tot_b_qty, tot_s_qty)
            m2_gross = (m2_b_vwap - m2_s_vwap) * m2_matched if m2_matched > 0 else 0.0
            m2_cost = m2_b_vwap * 0.0032 * m2_matched if m2_matched > 0 else 0.0
            m2_pnl = (m2_b_vwap * 0.9968 - m2_s_vwap) * m2_matched if m2_matched > 0 else 0.0

            dealer_agg = {}
            for a in alloc_rows:
                bcode = a["broker_code"]
                bname = a["broker_name"]
                if bcode not in dealer_agg:
                    dealer_agg[bcode] = {
                        "broker_code": bcode,
                        "broker_name": bname,
                        "buy_qty": 0,
                        "sell_qty": 0,
                        "total_volume": 0,
                        "method1_pnl": 0.0,
                    }
                dealer_agg[bcode]["buy_qty"] += a["buy_qty"]
                dealer_agg[bcode]["sell_qty"] += a["sell_qty"]
                dealer_agg[bcode]["total_volume"] += a["total_volume"]
                dealer_agg[bcode]["method1_pnl"] += a["allocated_pnl"]

            tot_dealer_vol = sum(d["total_volume"] for d in dealer_agg.values())
            dealer_list = []
            for bcode, d in dealer_agg.items():
                share = (d["total_volume"] / tot_dealer_vol) if tot_dealer_vol > 0 else 0.0
                d["volume_share"] = share
                d["method2_pnl"] = m2_pnl * share
                d["pnl_diff"] = d["method2_pnl"] - d["method1_pnl"]
                dealer_list.append(d)
            dealer_list.sort(key=lambda x: max(x["method1_pnl"], x["method2_pnl"]), reverse=True)

            return {
                "daily_rows": daily_rows,
                "method1": {
                    "matched_qty": m1_matched,
                    "gross_spread_pnl": m1_gross,
                    "transaction_cost": m1_cost,
                    "total_estimated_mm_pnl": m1_pnl,
                },
                "method2": {
                    "total_buy_qty": tot_b_qty,
                    "total_buy_amount": tot_b_amt,
                    "buy_vwap": m2_b_vwap,
                    "total_sell_qty": tot_s_qty,
                    "total_sell_amount": tot_s_amt,
                    "sell_vwap": m2_s_vwap,
                    "matched_qty": m2_matched,
                    "gross_spread_pnl": m2_gross,
                    "transaction_cost": m2_cost,
                    "total_estimated_mm_pnl": m2_pnl,
                },
                "pnl_diff": m2_pnl - m1_pnl,
                "dealers": dealer_list
            }

    def get_broker_range_history(self, start_date: str, end_date: str, broker_code: str) -> Dict[str, Any]:
        """Returns trading history and allocations for a broker in a date range."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    a.trade_date,
                    a.stock_id,
                    s.stock_name,
                    a.buy_qty,
                    a.sell_qty,
                    a.total_volume,
                    a.volume_share,
                    a.allocated_pnl
                FROM daily_mm_allocation a
                LEFT JOIN stock_master s ON a.stock_id = s.stock_id
                WHERE a.trade_date >= ? AND a.trade_date <= ? AND a.broker_code = ?
                ORDER BY a.trade_date ASC, a.allocated_pnl DESC
                """,
                (start_date, end_date, broker_code)
            )
            alloc_history = [dict(r) for r in cur.fetchall()]

            cur = conn.execute(
                """
                SELECT
                    t.trade_date,
                    t.stock_id,
                    s.stock_name,
                    t.buy_qty,
                    t.buy_avg_price,
                    t.sell_qty,
                    t.sell_avg_price,
                    t.net_qty
                FROM daily_broker_trades t
                LEFT JOIN stock_master s ON t.stock_id = s.stock_id
                WHERE t.trade_date >= ? AND t.trade_date <= ? AND t.broker_code = ?
                ORDER BY t.trade_date ASC, ABS(t.net_qty) DESC
                """,
                (start_date, end_date, broker_code)
            )
            chip_history = [dict(r) for r in cur.fetchall()]

            return {
                "allocations": alloc_history,
                "chip_trades": chip_history
            }

db = DBManager()

