"""
Match invoices marked "paid" to real bank credits, then derive each customer's
actual payment behaviour from the bank date (not the claimed paid_date).

    from ml.reconcile import reconcile
    rec = reconcile(data)            # data = load_all(...)
    rec["unmatched_paid"]            # paid invoices with NO bank credit  -> anomaly flags
    rec["customer_delays"]           # avg days late per customer         -> forecast input
    rec["overall_avg_delay"]         # fallback for customers with no history
"""
import pandas as pd

from . import config


def _name_match(customer: str, counterparty: str) -> bool:
    a, b = str(customer).lower().strip(), str(counterparty).lower().strip()
    return bool(a) and bool(b) and (a in b or b in a)


def reconcile(data: dict) -> dict:
    tx = data["transactions"]
    inv = data["invoices"]

    credits = tx[tx["amount"] > 0].copy()
    credits["used"] = False
    first_txn_date = tx["date"].min()

    paid = inv[inv["status"] == "paid"].sort_values("paid_date")
    rows = []

    for _, r in paid.iterrows():
        base = {
            "invoice_id": r.invoice_id, "customer": r.customer, "amount": r.amount,
            "due_date": r.due_date, "claimed_paid_date": r.paid_date,
            "txn_id": None, "bank_date": pd.NaT, "delay_days": None,
        }
        # Paid before our bank history starts: cannot verify, don't flag it
        if pd.notna(r.paid_date) and r.paid_date < first_txn_date - pd.Timedelta(days=config.RECON_DATE_WINDOW_DAYS):
            rows.append({**base, "match": "outside_window"})
            continue

        window = pd.Timedelta(days=config.RECON_DATE_WINDOW_DAYS)
        cand = credits[
            (~credits["used"])
            & ((credits["amount"] - r.amount).abs() <= r.amount * config.RECON_AMOUNT_TOLERANCE)
            & ((credits["date"] - r.paid_date).abs() <= window)
        ]
        if cand.empty:
            rows.append({**base, "match": "unmatched"})
            continue

        # Prefer same-name counterparty, then closest date
        cand = cand.assign(
            name_ok=cand["counterparty"].apply(lambda c: _name_match(r.customer, c)),
            gap=(cand["date"] - r.paid_date).abs(),
        ).sort_values(["name_ok", "gap"], ascending=[False, True])
        best = cand.iloc[0]
        credits.loc[best.name, "used"] = True
        rows.append({
            **base, "match": "matched", "txn_id": best.txn_id, "bank_date": best.date,
            "delay_days": int((best.date - r.due_date).days),
        })

    matches = pd.DataFrame(rows)
    verified = matches[matches["match"] == "matched"] if not matches.empty else matches

    if verified.empty:
        customer_delays = pd.DataFrame(columns=["customer", "avg_delay_days", "n_paid"])
        overall = 0.0
    else:
        customer_delays = (
            verified.groupby("customer")["delay_days"]
            .agg(avg_delay_days="mean", n_paid="count").round(1).reset_index()
        )
        overall = round(float(verified["delay_days"].mean()), 1)

    unmatched = matches[matches["match"] == "unmatched"] if not matches.empty else matches
    return {
        "matches": matches,
        "unmatched_paid": unmatched.reset_index(drop=True),
        "customer_delays": customer_delays,
        "overall_avg_delay": overall,
    }