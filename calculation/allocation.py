from typing import List, Dict, Any
from data_fetcher.broker import get_broker_name

def allocate_estimated_mm_pnl(
    total_estimated_mm_pnl: float,
    t_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Step C & D from specification:
    Allocates total Estimated MM PnL across all T-ending broker records based on their volume share.
    """
    # Group by broker_code in case a broker has multiple rows
    t_broker_agg: Dict[str, Dict[str, Any]] = {}

    for r in t_records:
        bcode = r["broker_code"]
        if bcode not in t_broker_agg:
            t_broker_agg[bcode] = {
                "broker_code": bcode,
                "broker_name": get_broker_name(bcode),
                "buy_qty": 0,
                "sell_qty": 0,
            }
        t_broker_agg[bcode]["buy_qty"] += r["buy_qty"]
        t_broker_agg[bcode]["sell_qty"] += r["sell_qty"]

    total_dealer_volume = sum(
        b["buy_qty"] + b["sell_qty"] for b in t_broker_agg.values()
    )

    allocations = []
    for bcode, b in t_broker_agg.items():
        vol = b["buy_qty"] + b["sell_qty"]
        share = (vol / total_dealer_volume) if total_dealer_volume > 0 else 0.0
        allocated_pnl = total_estimated_mm_pnl * share

        allocations.append({
            "broker_code": bcode,
            "broker_name": b["broker_name"],
            "buy_qty": b["buy_qty"],
            "sell_qty": b["sell_qty"],
            "total_volume": vol,
            "volume_share": share,
            "allocated_pnl": allocated_pnl,
        })

    allocations.sort(key=lambda x: x["total_volume"], reverse=True)
    return allocations
