"""
Turn the cleaned tables + reconciliation into the numbers the forecast and the
health score both consume.

    from ml.features import compute_features
    feats = compute_features(data, rec)            # as_of defaults to last transaction date
    feats["metrics"]                                # goes straight into the output contract
"""
import pandas as pd

from . import config

FIXED_CATEGORIES = {"rent", "payroll", "loan_emi", "tax"}


def _bucket(days_overdue: int) -> str:
    # Not-yet-due invoices fall into the first bucket so the 4 contract keys cover everything
    if days_overdue <= 30:
        return "0-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def compute_features(data: dict, rec: dict, as_of=None) -> dict:
    tx, inv, obl = data["transactions"], data["invoices"], data["obligations"]
    as_of = pd.Timestamp(as_of) if as_of else tx["date"].max()
    start = as_of - pd.Timedelta(days=config.LOOKBACK_DAYS - 1)
    months = config.LOOKBACK_DAYS / 30

    recent = tx[(tx["date"] >= start) & (tx["date"] <= as_of)]
    balance = float(tx[tx["date"] <= as_of]["balance"].iloc[-1])

    # ---- receivables ----
    open_inv = inv[inv["status"] == "open"].copy()
    open_inv["days_overdue"] = (as_of - open_inv["due_date"]).dt.days
    open_total = float(open_inv["amount"].sum())

    aging = {b: 0.0 for b in config.AGING_BUCKETS}
    for _, r in open_inv.iterrows():
        aging[_bucket(max(int(r.days_overdue), 0))] += float(r.amount)

    overdue_amt = float(open_inv.loc[open_inv["days_overdue"] > 0, "amount"].sum())
    late_amt = float(open_inv.loc[open_inv["days_overdue"] >= config.LATE_THRESHOLD_DAYS, "amount"].sum())

    # ---- revenue, concentration, DSO ----
    invoiced = inv[(inv["issue_date"] >= start) & (inv["issue_date"] <= as_of)]
    invoiced_total = float(invoiced["amount"].sum())
    by_customer = invoiced.groupby("customer")["amount"].sum().sort_values(ascending=False)
    top_share = float(by_customer.iloc[0] / invoiced_total) if invoiced_total else 0.0
    top_customer = by_customer.index[0] if len(by_customer) else None
    dso = (open_total / (invoiced_total / config.LOOKBACK_DAYS)) if invoiced_total else None

    # ---- cash flow ----
    credits = float(recent.loc[recent["amount"] > 0, "amount"].sum())
    debits = recent[recent["amount"] < 0]
    total_out = float(-debits["amount"].sum())
    emi_out = float(-debits.loc[debits["category"] == "loan_emi", "amount"].sum())
    monthly_inflow = credits / months
    monthly_opex = (total_out - emi_out) / months          # everything except loan EMI
    daily_out = total_out / config.LOOKBACK_DAYS
    buffer_days = balance / daily_out if daily_out else None

    monthly_emi = float(obl.loc[(obl["type"] == "emi") & (obl["frequency"] == "monthly"), "amount"].sum())
    dscr = ((monthly_inflow - monthly_opex) / monthly_emi) if monthly_emi else None

    weekly = recent[recent["amount"] > 0].set_index("date")["amount"].resample("W").sum()
    inflow_cv = float(weekly.std() / weekly.mean()) if len(weekly) > 1 and weekly.mean() else 0.0

    # variable (non-fixed) daily spend: baseline for the forecast
    variable = debits[~debits["category"].isin(FIXED_CATEGORIES)]
    baseline_start = as_of - pd.Timedelta(days=config.BASELINE_WINDOW_DAYS - 1)
    variable_daily = float(-variable.loc[variable["date"] >= baseline_start, "amount"].sum() / config.BASELINE_WINDOW_DAYS)

    r1 = lambda v, n=1: None if v is None else round(float(v), n)
    return {
        "as_of": as_of,
        "current_balance": balance,
        "receivables_aging": aging,
        "open_receivables": open_total,
        "overdue_share": round(overdue_amt / open_total, 3) if open_total else 0.0,
        "late_share": round(late_amt / open_total, 3) if open_total else 0.0,
        "top_customer": top_customer,
        "monthly_inflow": monthly_inflow,
        "monthly_opex": monthly_opex,
        "monthly_emi": monthly_emi,
        "inflow_cv": round(inflow_cv, 2),
        "variable_daily_spend": variable_daily,
        "unmatched_paid_count": int(len(rec["unmatched_paid"])),
        "metrics": {   # keys match the output contract
            "dso_days": r1(dso, 0),
            "top_customer_share": round(top_share, 2),
            "cash_buffer_days": r1(buffer_days, 1),
            "dscr": r1(dscr, 2),
            "avg_payment_delay_days": r1(rec["overall_avg_delay"], 1),
        },
    }