"""
30-day daily cash forecast.

    inflows  : each open invoice lands on  due_date + that customer's avg delay
    outflows : known obligations on their due dates + moving-average variable spend
    bands    : Monte Carlo over payment delays and spend (P10 / P90)

    from ml.forecast import forecast_cash
    fc = forecast_cash(data, feats, rec, loan_amount=None)
"""
import numpy as np
import pandas as pd

from . import config
from .utils import emi


def _customer_delay_stats(rec: dict) -> dict:
    """customer -> (mean_delay, std_delay) from verified (bank-matched) payments."""
    m = rec["matches"]
    verified = m[m["match"] == "matched"] if len(m) else m
    overall_mean = rec["overall_avg_delay"]
    overall_std = float(verified["delay_days"].std()) if len(verified) > 1 else 5.0
    overall_std = max(0.0 if np.isnan(overall_std) else overall_std, config.MIN_DELAY_STD_DAYS)
    stats = {}
    for cust, g in verified.groupby("customer") if len(verified) else []:
        std = float(g["delay_days"].std()) if len(g) > 1 else overall_std
        stats[cust] = (float(g["delay_days"].mean()), max(std if not np.isnan(std) else overall_std,
                                                          config.MIN_DELAY_STD_DAYS))
    return stats, (overall_mean, overall_std)


def _expand_obligations(obl: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list:
    """All obligation payments falling in (start, end]."""
    items = []
    for _, o in obl.iterrows():
        d = o.next_due_date
        step = {"monthly": pd.DateOffset(months=1), "weekly": pd.DateOffset(weeks=1)}.get(o.frequency)
        while step is not None and d <= start:      # roll stale dates forward
            d = d + step
        while start < d <= end:
            items.append({"name": o["name"], "type": o["type"], "date": d, "amount": float(o.amount)})
            if step is None:
                break
            d = d + step
    return items


def forecast_cash(data: dict, feats: dict, rec: dict, loan_amount=None, horizon=None) -> dict:
    horizon = horizon or config.FORECAST_HORIZON_DAYS
    as_of = feats["as_of"]
    dates = pd.date_range(as_of + pd.Timedelta(days=1), periods=horizon)
    end = dates[-1]
    inv = data["invoices"]
    open_inv = inv[inv["status"] == "open"].reset_index(drop=True)

    stats, (overall_mean, overall_std) = _customer_delay_stats(rec)

    # ---- obligations (+ optional what-if loan) ----
    obl_items = _expand_obligations(data["obligations"], as_of, end)
    inflow_items = []
    if loan_amount:
        loan_emi = emi(loan_amount, config.WHATIF_LOAN_RATE, config.WHATIF_LOAN_TENOR_MONTHS)
        first = as_of + pd.Timedelta(days=30)
        if first <= end:
            obl_items.append({"name": "New loan EMI", "type": "emi", "date": first, "amount": loan_emi})
        inflow_items.append({"invoice_id": None, "customer": "Loan disbursal", "expected_date": dates[0],
                             "amount": float(loan_amount), "days_overdue": 0})

    obl_by_day = np.zeros(horizon)
    for it in obl_items:
        obl_by_day[(it["date"] - as_of).days - 1] += it["amount"]

    # ---- open invoices -> expected arrival ----
    inv_rows = []
    for _, r in open_inv.iterrows():
        mean, std = stats.get(r.customer, (overall_mean, overall_std))
        days_overdue = int((as_of - r.due_date).days)
        expected = r.due_date + pd.Timedelta(days=round(mean))
        past_expected = expected <= as_of
        if past_expected:
            expected = as_of + pd.Timedelta(days=config.OVERDUE_CATCHUP_DAYS)
        inv_rows.append((r, mean, std, expected, past_expected, days_overdue))
        if expected <= end:
            inflow_items.append({"invoice_id": r.invoice_id, "customer": r.customer, "expected_date": expected,
                                 "amount": float(r.amount), "days_overdue": days_overdue})

    inflow_by_day = np.zeros(horizon)
    for it in inflow_items:
        inflow_by_day[(it["expected_date"] - as_of).days - 1] += it["amount"]

    variable = feats["variable_daily_spend"]
    outflow_by_day = obl_by_day + variable
    balance = feats["current_balance"] + np.cumsum(inflow_by_day - outflow_by_day)

    # ---- Monte Carlo ----
    rng = np.random.default_rng(config.MC_SEED)
    runs = config.MONTE_CARLO_RUNS
    paths = np.zeros((runs, horizon))
    for k in range(runs):
        infl = np.zeros(horizon)
        for r, mean, std, _, _, _ in inv_rows:
            arrival = (r.due_date - as_of).days + rng.normal(mean, std)       # days from as_of
            if arrival <= 0:                                                    # already past: lands soon
                arrival = rng.uniform(config.OVERDUE_CATCHUP_DAYS - 9, config.OVERDUE_CATCHUP_DAYS + 9)
            idx = int(round(arrival)) - 1
            if 0 <= idx < horizon:
                infl[idx] += r.amount
        if loan_amount:
            infl[0] += loan_amount
        spend = variable * max(0.5, rng.normal(1.0, config.VARIABLE_SPEND_NOISE))
        paths[k] = feats["current_balance"] + np.cumsum(infl - (obl_by_day + spend))

    lower, upper = np.percentile(paths, 10, axis=0), np.percentile(paths, 90, axis=0)
    prob_gap = float((paths.min(axis=1) < 0).mean())

    iso = lambda d: d.strftime("%Y-%m-%d")
    return {
        "dates": [iso(d) for d in dates],
        "balance": [round(float(x)) for x in balance],
        "lower": [round(float(x)) for x in lower],
        "upper": [round(float(x)) for x in upper],
        "inflows": [round(float(x)) for x in inflow_by_day],
        "outflows": [round(float(x)) for x in outflow_by_day],
        "prob_gap": round(prob_gap, 2),
        "inflow_items": inflow_items,        # used by gap_detection / explain
        "outflow_items": obl_items,
        "start_balance": feats["current_balance"],
    }