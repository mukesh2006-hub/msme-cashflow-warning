"""
Find the liquidity gap in a forecast and say what causes it.

    from ml.gap_detection import detect_gap
    gap = detect_gap(fc, feats, rec)       # matches the "gap" block of the output contract
"""
import pandas as pd

from . import config
from .utils import fmt_inr


def detect_gap(fc: dict, feats: dict, rec: dict) -> dict:
    dates = pd.to_datetime(fc["dates"])
    bal = fc["balance"]
    min_bal = min(bal)
    min_date = dates[bal.index(min_bal)]

    first_gap = next((d for d, b in zip(dates, bal) if b < 0), None)
    daily_out = (feats["monthly_opex"] + feats["monthly_emi"]) / 30
    buffer_amt = config.MIN_CASH_BUFFER_DAYS * daily_out
    first_low = next((d for d, b in zip(dates, bal) if b < buffer_amt), None)

    causes = []
    anchor = first_gap or first_low
    if anchor is not None:
        # 1) big obligations landing shortly before / on the gap date
        for o in sorted(fc["outflow_items"], key=lambda x: x["date"]):
            if anchor - pd.Timedelta(days=10) <= o["date"] <= anchor and o["amount"] >= 0.05 * feats["monthly_opex"]:
                causes.append(f"{o['name']} of {fmt_inr(o['amount'])} due on {o['date'].strftime('%d %b')}")

        # 2) late customers whose money is not expected before the gap
        delays = {r.customer: r.avg_delay_days for r in rec["customer_delays"].itertuples()}
        late = {}
        for it in fc["inflow_items"]:
            if it["days_overdue"] >= config.LATE_THRESHOLD_DAYS and it["expected_date"] > anchor - pd.Timedelta(days=1):
                late.setdefault(it["customer"], []).append(it)
        for cust, items in late.items():
            total = sum(i["amount"] for i in items)
            causes.append(f"{len(items)} invoice(s) worth {fmt_inr(total)} from {cust} are "
                          f"{max(i['days_overdue'] for i in items)} days overdue"
                          + (f" (usually pays ~{delays[cust]:.0f} days late)" if cust in delays else ""))

        # 3) thin buffer
        if feats["metrics"]["cash_buffer_days"] is not None and feats["metrics"]["cash_buffer_days"] < config.MIN_CASH_BUFFER_DAYS:
            causes.append(f"Cash covers only {feats['metrics']['cash_buffer_days']:.0f} day(s) of expenses "
                          f"(target {config.MIN_CASH_BUFFER_DAYS}+)")

    iso = lambda d: None if d is None else d.strftime("%Y-%m-%d")
    return {
        "has_gap": first_gap is not None,
        "first_gap_date": iso(first_gap),
        "min_balance": int(min_bal),
        "min_balance_date": iso(min_date),
        "gap_amount": int(max(-min_bal, 0)),
        "below_buffer_date": iso(first_low),
        "prob_gap": fc["prob_gap"],
        "causes": causes,
    }