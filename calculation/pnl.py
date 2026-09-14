from typing import List, Dict, Any

TRANSACTION_COST_RATE = 0.0032

def calculate_stock_estimated_mm_pnl(priced_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Step A & B from specification:
    Calculates customer (broker) Buy VWAP, Sell VWAP, Matched Qty,
    and Estimated Market-Making PnL for a single stock using priced records only.
    """
    customer_buy_qty = sum(r["buy_qty"] for r in priced_records)
    customer_buy_amount = sum(r["buy_qty"] * r["price"] for r in priced_records if r.get("price") is not None)

    customer_sell_qty = sum(r["sell_qty"] for r in priced_records)
    customer_sell_amount = sum(r["sell_qty"] * r["price"] for r in priced_records if r.get("price") is not None)

    customer_buy_avg = (customer_buy_amount / customer_buy_qty) if customer_buy_qty > 0 else 0.0
    customer_sell_avg = (customer_sell_amount / customer_sell_qty) if customer_sell_qty > 0 else 0.0

    matched_qty = min(customer_buy_qty, customer_sell_qty)

    if matched_qty > 0 and customer_buy_qty > 0 and customer_sell_qty > 0:
        gross_spread_pnl = (customer_buy_avg - customer_sell_avg) * matched_qty
        transaction_cost = customer_buy_avg * TRANSACTION_COST_RATE * matched_qty
        total_estimated_mm_pnl = (customer_buy_avg * (1.0 - TRANSACTION_COST_RATE) - customer_sell_avg) * matched_qty
    else:
        gross_spread_pnl = 0.0
        transaction_cost = 0.0
        total_estimated_mm_pnl = 0.0

    return {
        "customer_buy_qty": customer_buy_qty,
        "customer_buy_amount": customer_buy_amount,
        "customer_buy_avg": customer_buy_avg,
        "customer_sell_qty": customer_sell_qty,
        "customer_sell_amount": customer_sell_amount,
        "customer_sell_avg": customer_sell_avg,
        "matched_qty": matched_qty,
        "gross_spread_pnl": gross_spread_pnl,
        "transaction_cost": transaction_cost,
        "total_estimated_mm_pnl": total_estimated_mm_pnl,
    }
