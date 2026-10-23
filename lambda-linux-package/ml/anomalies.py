"""
Data-integrity and risk flags.

    from ml.anomalies import find_anomalies, INTEGRITY_TYPES
    flags = find_anomalies(data, rec, feats)
    integrity = [a for a in flags if a["type"] in INTEGRITY_TYPES]   # these feed data_consistency

Each flag: {"type", "severity", "ref_id", "message"}
"""
import pandas as pd

from . import config
from .utils import fmt_inr

INTEGRITY_TYPES = {"paid_no_credit", "duplicate"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def find_anomalies(data: dict, rec: dict, feats: dict) -> list:
    flags = []

    # 1) Invoices claimed as paid but with no bank credit
    for r in rec["unmatched_paid"].itertuples():
        flags.append({
            "type": "paid_no_credit", "severity": "high", "ref_id": r.invoice_id,
            "message": f"Invoice {r.invoice_id} ({fmt_inr(r.amount)}, {r.customer}) is marked paid "
                       f"but no matching bank credit was found.",
        })

    # 2) Possible duplicate transactions (same counterparty + amount within a few days)
    tx = data["transactions"].sort_values("date")
    window = pd.Timedelta(days=config.DUPLICATE_WINDOW_DAYS)
    big = 0.05 * feats["monthly_opex"]
    for (cp, amt), g in tx.groupby(["counterparty", "amount"]):
        if len(g) < 2:
            continue
        rows = list(g.itertuples())
        for prev, cur in zip(rows, rows[1:]):
            if cur.date - prev.date <= window:
                flags.append({
                    "type": "duplicate", "severity": "medium" if abs(amt) >= big else "low", "ref_id": cur.txn_id,
                    "message": f"{fmt_inr(abs(amt))} {'payment to' if amt < 0 else 'receipt from'} {cp} appears twice "
                               f"within {config.DUPLICATE_WINDOW_DAYS} days ({prev.txn_id}, {cur.txn_id}).",
                })

    # 3) Customer concentration
    share, cust = feats["metrics"]["top_customer_share"], feats["top_customer"]
    if share > config.CONCENTRATION_LIMIT and cust:
        flags.append({
            "type": "concentration", "severity": "high" if share > 0.5 else "medium", "ref_id": cust,
            "message": f"{share * 100:.0f}% of recent revenue comes from {cust} "
                       f"(limit {config.CONCENTRATION_LIMIT * 100:.0f}%).",
        })

    return sorted(flags, key=lambda a: SEVERITY_ORDER[a["severity"]])