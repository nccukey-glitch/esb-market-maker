from typing import List, Dict, Any, Tuple
from collections import defaultdict

TRANSACTION_COST_RATE = 0.0032

def calculate_single_stock_range_pnl_method1(
    daily_records_by_date: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Method 1: 逐日計算損益累加 (Daily Cumulative Method)
    Calculates daily VWAP, matched qty, and estimated MM PnL for each day,
    then sums them up over the entire date range.
    
    daily_records_by_date is expected to be:
    {
        trade_date: {
            "priced_records": [...],
            "t_records": [...]
        }
    }
    """
    total_matched_qty = 0
    total_gross_spread_pnl = 0.0
    total_transaction_cost = 0.0
    total_estimated_mm_pnl = 0.0
    
    # Dealer cumulative tracking
    dealer_volumes = defaultdict(int)
    dealer_pnls = defaultdict(float)
    dealer_names = {}
    
    daily_breakdown = []
    
    for dt in sorted(daily_records_by_date.keys()):
        day_data = daily_records_by_date[dt]
        priced = day_data.get("priced_records", [])
        t_records = day_data.get("t_records", [])
        
        # 1. Day VWAP
        day_b_qty = sum(r["buy_qty"] for r in priced)
        day_b_amt = sum(r["buy_qty"] * r["price"] for r in priced if r.get("price") is not None)
        day_s_qty = sum(r["sell_qty"] for r in priced)
        day_s_amt = sum(r["sell_qty"] * r["price"] for r in priced if r.get("price") is not None)
        
        b_vwap = (day_b_amt / day_b_qty) if day_b_qty > 0 else 0.0
        s_vwap = (day_s_amt / day_s_qty) if day_s_qty > 0 else 0.0
        matched = min(day_b_qty, day_s_qty)
        
        if matched > 0 and day_b_qty > 0 and day_s_qty > 0:
            gross = (b_vwap - s_vwap) * matched
            cost = b_vwap * TRANSACTION_COST_RATE * matched
            day_pnl = (b_vwap * (1.0 - TRANSACTION_COST_RATE) - s_vwap) * matched
        else:
            gross = 0.0
            cost = 0.0
            day_pnl = 0.0
            
        total_matched_qty += matched
        total_gross_spread_pnl += gross
        total_transaction_cost += cost
        total_estimated_mm_pnl += day_pnl
        
        # 2. Day dealer allocations
        day_dealer_vol = defaultdict(int)
        for r in t_records:
            bcode = r["broker_code"]
            bname = r.get("broker_name", bcode)
            dealer_names[bcode] = bname
            vol = r["buy_qty"] + r["sell_qty"]
            day_dealer_vol[bcode] += vol
            dealer_volumes[bcode] += vol
            
        day_total_t_vol = sum(day_dealer_vol.values())
        day_allocations = []
        for bcode, vol in day_dealer_vol.items():
            share = (vol / day_total_t_vol) if day_total_t_vol > 0 else 0.0
            pnl_alloc = day_pnl * share
            dealer_pnls[bcode] += pnl_alloc
            day_allocations.append({
                "broker_code": bcode,
                "broker_name": dealer_names[bcode],
                "volume": vol,
                "share": share,
                "allocated_pnl": pnl_alloc
            })
            
        daily_breakdown.append({
            "trade_date": dt,
            "buy_qty": day_b_qty,
            "buy_vwap": b_vwap,
            "sell_qty": day_s_qty,
            "sell_vwap": s_vwap,
            "matched_qty": matched,
            "gross_spread_pnl": gross,
            "transaction_cost": cost,
            "total_estimated_mm_pnl": day_pnl,
            "allocations": day_allocations
        })
        
    # Summarize allocations across all days
    total_dealer_volume = sum(dealer_volumes.values())
    dealer_summary = []
    for bcode, vol in dealer_volumes.items():
        share = (vol / total_dealer_volume) if total_dealer_volume > 0 else 0.0
        dealer_summary.append({
            "broker_code": bcode,
            "broker_name": dealer_names.get(bcode, bcode),
            "total_volume": vol,
            "volume_share": share,
            "allocated_pnl": dealer_pnls[bcode]
        })
    dealer_summary.sort(key=lambda x: x["allocated_pnl"], reverse=True)

    return {
        "method": "method1_daily_sum",
        "method_name": "逐日累加法",
        "matched_qty": total_matched_qty,
        "gross_spread_pnl": total_gross_spread_pnl,
        "transaction_cost": total_transaction_cost,
        "total_estimated_mm_pnl": total_estimated_mm_pnl,
        "dealer_allocations": dealer_summary,
        "daily_breakdown": daily_breakdown
    }

def calculate_single_stock_range_pnl_method2(
    daily_records_by_date: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Method 2: 日期區間買賣依公式合計計算 (Pooled Range Aggregate Formula)
    Aggregates all customer buy quantities/amounts and sell quantities/amounts over the entire range,
    computes range pooled Buy/Sell VWAP and range matched qty, then calculates range PnL.
    Allocates to dealers based on their cumulative volume share over the range.
    """
    total_buy_qty = 0
    total_buy_amount = 0.0
    total_sell_qty = 0
    total_sell_amount = 0.0
    
    dealer_volumes = defaultdict(int)
    dealer_buy_qty = defaultdict(int)
    dealer_sell_qty = defaultdict(int)
    dealer_names = {}
    
    for dt, day_data in daily_records_by_date.items():
        priced = day_data.get("priced_records", [])
        t_records = day_data.get("t_records", [])
        
        for r in priced:
            p = r.get("price")
            if p is not None:
                total_buy_qty += r["buy_qty"]
                total_buy_amount += r["buy_qty"] * p
                total_sell_qty += r["sell_qty"]
                total_sell_amount += r["sell_qty"] * p
                
        for r in t_records:
            bcode = r["broker_code"]
            dealer_names[bcode] = r.get("broker_name", bcode)
            dealer_buy_qty[bcode] += r["buy_qty"]
            dealer_sell_qty[bcode] += r["sell_qty"]
            dealer_volumes[bcode] += (r["buy_qty"] + r["sell_qty"])
            
    range_buy_vwap = (total_buy_amount / total_buy_qty) if total_buy_qty > 0 else 0.0
    range_sell_vwap = (total_sell_amount / total_sell_qty) if total_sell_qty > 0 else 0.0
    range_matched_qty = min(total_buy_qty, total_sell_qty)
    
    if range_matched_qty > 0 and total_buy_qty > 0 and total_sell_qty > 0:
        gross = (range_buy_vwap - range_sell_vwap) * range_matched_qty
        cost = range_buy_vwap * TRANSACTION_COST_RATE * range_matched_qty
        range_total_pnl = (range_buy_vwap * (1.0 - TRANSACTION_COST_RATE) - range_sell_vwap) * range_matched_qty
    else:
        gross = 0.0
        cost = 0.0
        range_total_pnl = 0.0
        
    total_dealer_volume = sum(dealer_volumes.values())
    dealer_summary = []
    for bcode, vol in dealer_volumes.items():
        share = (vol / total_dealer_volume) if total_dealer_volume > 0 else 0.0
        allocated_pnl = range_total_pnl * share
        dealer_summary.append({
            "broker_code": bcode,
            "broker_name": dealer_names.get(bcode, bcode),
            "buy_qty": dealer_buy_qty[bcode],
            "sell_qty": dealer_sell_qty[bcode],
            "total_volume": vol,
            "volume_share": share,
            "allocated_pnl": allocated_pnl
        })
    dealer_summary.sort(key=lambda x: x["allocated_pnl"], reverse=True)

    return {
        "method": "method2_pooled_formula",
        "method_name": "區間總額公式法",
        "customer_buy_qty": total_buy_qty,
        "customer_buy_amount": total_buy_amount,
        "customer_buy_avg": range_buy_vwap,
        "customer_sell_qty": total_sell_qty,
        "customer_sell_amount": total_sell_amount,
        "customer_sell_avg": range_sell_vwap,
        "matched_qty": range_matched_qty,
        "gross_spread_pnl": gross,
        "transaction_cost": cost,
        "total_estimated_mm_pnl": range_total_pnl,
        "dealer_allocations": dealer_summary
    }

def calculate_dual_range_pnl(
    daily_records_by_date: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes both Method 1 and Method 2 and returns side-by-side comparative analytics.
    """
    m1 = calculate_single_stock_range_pnl_method1(daily_records_by_date)
    m2 = calculate_single_stock_range_pnl_method2(daily_records_by_date)
    
    pnl_diff = m2["total_estimated_mm_pnl"] - m1["total_estimated_mm_pnl"]
    matched_diff = m2["matched_qty"] - m1["matched_qty"]
    
    # Merge dealer allocations for side-by-side view
    m1_dealers = {d["broker_code"]: d for d in m1["dealer_allocations"]}
    m2_dealers = {d["broker_code"]: d for d in m2["dealer_allocations"]}
    all_dealers = sorted(set(list(m1_dealers.keys()) + list(m2_dealers.keys())))
    
    dealer_comparison = []
    for bcode in all_dealers:
        d1 = m1_dealers.get(bcode, {})
        d2 = m2_dealers.get(bcode, {})
        bname = d1.get("broker_name") or d2.get("broker_name") or bcode
        pnl1 = d1.get("allocated_pnl", 0.0)
        pnl2 = d2.get("allocated_pnl", 0.0)
        vol = d2.get("total_volume") or d1.get("total_volume", 0)
        dealer_comparison.append({
            "broker_code": bcode,
            "broker_name": bname,
            "total_volume": vol,
            "method1_pnl": pnl1,
            "method2_pnl": pnl2,
            "pnl_diff": pnl2 - pnl1
        })
    dealer_comparison.sort(key=lambda x: max(x["method1_pnl"], x["method2_pnl"]), reverse=True)

    return {
        "method1": m1,
        "method2": m2,
        "pnl_diff": pnl_diff,
        "matched_diff": matched_diff,
        "dealer_comparison": dealer_comparison
    }
