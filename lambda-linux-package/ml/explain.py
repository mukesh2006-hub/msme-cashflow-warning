"""
Plain-language output: explanation cards, warnings with recommended actions,
and the safe-loan calculator. Every sentence is built from a computed number.

    explanations = build_explanations(data, feats, gap, rec, anomalies)
    warnings     = build_warnings(data, feats, gap, fc, rec, anomalies)
    safe         = safe_loan_amount(feats)
"""
import math

import pandas as pd

from . import config
from .utils import emi, fmt_inr

ORDER = {"high": 0, "medium": 1, "low": 2}


def _late_by_customer(data: dict, feats: dict) -> dict:
    """customer -> {amount, count, max_days} for open invoices overdue by the late threshold or more."""
    inv = data["invoices"]
    o = inv[inv["status"] == "open"].copy()
    o["days_overdue"] = (feats["as_of"] - o["due_date"]).dt.days
    o = o[o["days_overdue"] >= config.LATE_THRESHOLD_DAYS]
    return {c: {"amount": float(g["amount"].sum()), "count": len(g), "max_days": int(g["days_overdue"].max())}
            for c, g in o.groupby("customer")}


def build_explanations(data, feats, gap, rec, anomalies) -> list:
    m, out = feats["metrics"], []
    add = lambda sev, title, msg, metric, value: out.append(
        {"severity": sev, "title": title, "message": msg, "metric": metric, "value": value})

    if feats["late_share"] >= 0.05:
        add("high" if feats["late_share"] >= 0.2 else "medium", "Collections are slow",
            f"Score dropped because {feats['late_share'] * 100:.0f}% of receivables are "
            f"{config.LATE_THRESHOLD_DAYS}+ days late.", "late_share", feats["late_share"])

    if m["cash_buffer_days"] is not None and m["cash_buffer_days"] < config.MIN_CASH_BUFFER_DAYS:
        add("high" if m["cash_buffer_days"] < 7 else "medium", "Thin cash buffer",
            f"Cash covers only {m['cash_buffer_days']:.0f} day(s) of expenses; "
            f"the safe level is {config.MIN_CASH_BUFFER_DAYS}+ days.", "cash_buffer_days", m["cash_buffer_days"])

    if m["dscr"] is not None and m["dscr"] < config.DSCR_RANGE[1]:
        below_one = m["dscr"] < 1
        add("high" if below_one else "medium", "Loan repayments are not comfortably covered",
            f"DSCR is {m['dscr']:.2f}" + (": operating cash flow does not cover the EMI." if below_one
                                           else f", below the {config.DSCR_RANGE[1]} comfort level."),
            "dscr", m["dscr"])

    if m["top_customer_share"] > config.CONCENTRATION_LIMIT and feats["top_customer"]:
        add("medium", "Customer concentration",
            f"{m['top_customer_share'] * 100:.0f}% of revenue comes from {feats['top_customer']}; "
            f"if they pay late, cash flow suffers.", "top_customer_share", m["top_customer_share"])

    unmatched = rec["unmatched_paid"]
    if len(unmatched):
        add("high", "Reported revenue not backed by the bank",
            f"{len(unmatched)} invoice(s) worth {fmt_inr(unmatched['amount'].sum())} are marked paid "
            f"but have no matching bank credit.", "unmatched_paid_count", len(unmatched))

    cd = rec["customer_delays"]
    if len(cd):
        worst = cd.sort_values("avg_delay_days", ascending=False).iloc[0]
        if worst.avg_delay_days >= 20:
            inv = data["invoices"]
            owed = inv[(inv["status"] == "open") & (inv["customer"] == worst.customer)]["amount"].sum()
            add("medium", "Chronic late payer",
                f"{worst.customer} pays {worst.avg_delay_days:.0f} days late on average"
                + (f" and still owes {fmt_inr(owed)}." if owed else "."),
                "avg_delay_days", float(worst.avg_delay_days))

    if not any(e["severity"] in ("high", "medium") for e in out):
        add("low", "Finances look healthy",
            f"No receivables are 30+ days late, cash covers {m['cash_buffer_days']:.0f} days of expenses, "
            f"and the forecast shows no cash gap.", "gap_prob", gap["prob_gap"])

    return sorted(out, key=lambda e: ORDER[e["severity"]])


def build_warnings(data, feats, gap, fc, rec, anomalies) -> list:
    m, out = feats["metrics"], []
    late = _late_by_customer(data, feats)
    top_late = max(late.items(), key=lambda kv: kv[1]["amount"]) if late else None
    fmt_d = lambda s: pd.Timestamp(s).strftime("%d %b")

    # 1) Liquidity gap / thin buffer
    if gap["has_gap"]:
        collect = (f"Collect the overdue {fmt_inr(top_late[1]['amount'])} from {top_late[0]} before {fmt_d(gap['first_gap_date'])}"
                   if top_late else "Bring forward receivables or delay a non-urgent payable")
        buffer = math.ceil(gap["gap_amount"] * 1.2 / 10000) * 10000
        out.append({"type": "liquidity_gap", "severity": "high", "date": gap["first_gap_date"],
                    "message": f"Cash is projected to go negative on {fmt_d(gap['first_gap_date'])} "
                               f"(shortfall up to {fmt_inr(gap['gap_amount'])}, {gap['prob_gap'] * 100:.0f}% likelihood).",
                    "action": f"{collect}, or arrange a short-term buffer of about {fmt_inr(buffer)}."})
    elif gap["below_buffer_date"]:
        out.append({"type": "liquidity_gap", "severity": "medium", "date": gap["below_buffer_date"],
                    "message": f"Cash falls below the {config.MIN_CASH_BUFFER_DAYS}-day safety buffer on "
                               f"{fmt_d(gap['below_buffer_date'])}.",
                    "action": "Collect receivables earlier or hold back discretionary spend to rebuild the buffer."})

    # 2) Repayment risk around the next EMI
    emis = sorted([o for o in fc["outflow_items"] if o["type"] == "emi"], key=lambda o: o["date"])
    if emis:
        e = emis[0]
        idx = (e["date"] - feats["as_of"]).days - 1
        bal_on = fc["balance"][idx]
        weak_dscr = m["dscr"] is not None and m["dscr"] < 1.0
        if bal_on < 0 or weak_dscr:
            out.append({"type": "repayment_risk", "severity": "high" if (bal_on < 0 or m["dscr"] < 0.5) else "medium",
                        "date": e["date"].strftime("%Y-%m-%d"),
                        "message": f"{e['name']} of {fmt_inr(e['amount'])} on {fmt_d(e['date'])} is at risk"
                                   + (f": projected balance that day is {fmt_inr(bal_on)}." if bal_on < 0
                                      else f" (DSCR {m['dscr']:.2f}, operating cash does not cover repayments)."),
                        "action": "Ask the lender to move the EMI date or restructure, and avoid new debt until collections improve."})

    # 3) Receivable risk
    if feats["late_share"] >= 0.2:
        who = f", mostly from {top_late[0]}" if top_late else ""
        out.append({"type": "receivable_risk", "severity": "high" if feats["late_share"] >= 0.3 else "medium", "date": None,
                    "message": f"{feats['late_share'] * 100:.0f}% of receivables ({fmt_inr(feats['late_share'] * feats['open_receivables'])}) "
                               f"are {config.LATE_THRESHOLD_DAYS}+ days late{who}.",
                    "action": "Send payment reminders now, escalate the oldest invoices, and pause new credit to repeat late payers."})

    # 4) Data integrity
    integ = [a for a in anomalies if a["type"] in ("paid_no_credit", "duplicate")]
    if integ:
        n_nc = sum(a["type"] == "paid_no_credit" for a in integ)
        out.append({"type": "data_integrity", "severity": "high" if n_nc else "low", "date": None,
                    "message": f"{len(integ)} data inconsistency flag(s): {n_nc} invoice(s) marked paid with no bank credit, "
                               f"{len(integ) - n_nc} possible duplicate transaction(s).",
                    "action": "Verify these records before sharing financials with a lender; unverified revenue weakens a loan application."})

    return sorted(out, key=lambda w: ORDER[w["severity"]])


def safe_loan_amount(feats: dict) -> int:
    """Largest principal whose EMI keeps DSCR >= SAFE_LOAN_MIN_DSCR, capped at N months of inflow."""
    surplus = feats["monthly_inflow"] - feats["monthly_opex"]
    max_total_emi = surplus / config.SAFE_LOAN_MIN_DSCR
    room = max_total_emi - feats["monthly_emi"]
    if room <= 0:
        return 0
    r, n = config.WHATIF_LOAN_RATE / 12, config.WHATIF_LOAN_TENOR_MONTHS
    principal = room * (1 - (1 + r) ** -n) / r
    principal = min(principal, config.SAFE_LOAN_MAX_MONTHS_OF_INFLOW * feats["monthly_inflow"])
    return int(principal // 10000 * 10000)