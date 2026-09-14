from typing import List, Dict, Any, Optional
from data_fetcher.broker import get_broker_name

def calculate_broker_chips(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calculates broker chip summary for a single stock from its trading records.
    Both priced brokers and T brokers are aggregated by broker_code.
    """
    broker_agg: Dict[str, Dict[str, Any]] = {}

    for r in records:
        bcode = r["broker_code"]
        is_t = r["is_t"]
        price = r["price"]
        b_qty = r["buy_qty"]
        s_qty = r["sell_qty"]

        if bcode not in broker_agg:
            broker_agg[bcode] = {
                "broker_code": bcode,
                "broker_name": get_broker_name(bcode),
                "is_t": is_t,
                "buy_qty": 0,
                "buy_amount": 0.0,
                "sell_qty": 0,
                "sell_amount": 0.0,
            }

        broker_agg[bcode]["buy_qty"] += b_qty
        broker_agg[bcode]["sell_qty"] += s_qty

        if price is not None and not is_t:
            broker_agg[bcode]["buy_amount"] += b_qty * price
            broker_agg[bcode]["sell_amount"] += s_qty * price

    total_buy_qty = sum(b["buy_qty"] for b in broker_agg.values())
    total_sell_qty = sum(b["sell_qty"] for b in broker_agg.values())

    results = []
    for bcode, data in broker_agg.items():
        b_qty = data["buy_qty"]
        b_amt = data["buy_amount"]
        s_qty = data["sell_qty"]
        s_amt = data["sell_amount"]

        buy_avg = (b_amt / b_qty) if (b_qty > 0 and not data["is_t"]) else None
        sell_avg = (s_amt / s_qty) if (s_qty > 0 and not data["is_t"]) else None

        buy_ratio = (b_qty / total_buy_qty) if total_buy_qty > 0 else 0.0
        sell_ratio = (s_qty / total_sell_qty) if total_sell_qty > 0 else 0.0
        net_qty = b_qty - s_qty

        results.append({
            "broker_code": bcode,
            "broker_name": data["broker_name"],
            "is_t": data["is_t"],
            "buy_qty": b_qty,
            "buy_amount": b_amt,
            "buy_avg_price": buy_avg,
            "buy_ratio": buy_ratio,
            "sell_qty": s_qty,
            "sell_amount": s_amt,
            "sell_avg_price": sell_avg,
            "sell_ratio": sell_ratio,
            "net_qty": net_qty,
        })

    return results

def get_net_buy_sell_rankings(chip_results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Splits chip results into:
    - net_buyers: sorted by net_qty descending (net_qty > 0 first)
    - net_sellers: sorted by net_qty ascending (net_qty < 0 first, represented with positive sell-excess)
    Ensures buy_ratio and sell_ratio are always present.
    """
    total_buy = sum(r.get("buy_qty", 0) for r in chip_results)
    total_sell = sum(r.get("sell_qty", 0) for r in chip_results)
    for r in chip_results:
        if "buy_ratio" not in r or r.get("buy_ratio") is None:
            r["buy_ratio"] = (r.get("buy_qty", 0) / total_buy) if total_buy > 0 else 0.0
        if "sell_ratio" not in r or r.get("sell_ratio") is None:
            r["sell_ratio"] = (r.get("sell_qty", 0) / total_sell) if total_sell > 0 else 0.0

    net_buyers = [r for r in chip_results if r["net_qty"] > 0]
    net_buyers.sort(key=lambda x: x["net_qty"], reverse=True)

    net_sellers = [r for r in chip_results if r["net_qty"] < 0]
    net_sellers.sort(key=lambda x: x["net_qty"])  # Most negative net_qty first

    neutral = [r for r in chip_results if r["net_qty"] == 0]

    return {
        "net_buyers": net_buyers,
        "net_sellers": net_sellers,
        "neutral": neutral,
        "all": sorted(chip_results, key=lambda x: abs(x["net_qty"]), reverse=True)
    }
