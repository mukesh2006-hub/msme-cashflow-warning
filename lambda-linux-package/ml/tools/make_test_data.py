"""
Generate two tiny, deterministic test MSMEs in the contract format (ml/schema.py):

    data/msme_stressed/   late payer + EMI due soon + planted data problems
    data/msme_healthy/    prompt payers + comfortable cash

Run from the repo root:
    python -m ml.tools.make_test_data

Replace with member A's generator later; downstream code won't change because
both follow ml/schema.py.
"""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

AS_OF = date(2026, 10, 23)
DAYS = 90
START = AS_OF - timedelta(days=DAYS - 1)
OUT = Path("data")

VARIABLE_EXPENSES = [
    ("supplies", "Raw material purchase", ["Sri Traders", "Metro Supplies", "Kaveri Agencies"], (2500, 9000)),
    ("utilities", "Utility bill", ["BESCOM", "Airtel"], (1500, 4000)),
    ("transport", "Freight / transport", ["SpeedLogistics", "Local Tempo"], (800, 3500)),
    ("misc", "Misc expense", ["Office Mart", "Tea & Snacks"], (300, 1500)),
]


def _d(offset_days_ago: int) -> date:
    return AS_OF - timedelta(days=offset_days_ago)


# (customer, issued N days ago, amount, delay after due date in days; None = still open)
# Due date is always issue + 30 days. Paid invoices must land on/before AS_OF.
SCENARIOS = {
    "msme_stressed": {
        "target_end_balance": 10_000,
        "invoices": [
            ("Client X", 100, 90_000, 36), ("Client X", 80, 85_000, 40),
            ("Client X", 75, 120_000, None), ("Client X", 62, 95_000, None),
            ("Client X", 20, 110_000, None),
            ("Client Y", 90, 60_000, 2), ("Client Y", 60, 62_000, 3),
            ("Client Y", 30, 70_000, None), ("Client Y", 10, 65_000, None),
            ("Client Z", 85, 55_000, 14), ("Client Z", 55, 57_000, 16),
            ("Client Z", 35, 58_000, None),
        ],
        # Marked paid but NO bank credit exists (planted inconsistency)
        "phantom_paid": [("Client W", 70, 48_000, 5), ("Client W", 50, 52_000, 5)],
        "duplicate_txn": True,
        "rent": 35_000, "payroll": 85_000, "emi": 45_000, "gst": 18_000,
        "daily_spend_scale": 1.0,
    },
    "msme_healthy": {
        "target_end_balance": 650_000,
        "invoices": [
            ("Client A", 90, 128_000, 1), ("Client A", 60, 136_000, 0), ("Client A", 30, 131_000, None),
            ("Client B", 85, 112_000, 2), ("Client B", 55, 115_000, 1), ("Client B", 25, 120_000, None),
            ("Client C", 80, 104_000, 3), ("Client C", 50, 109_000, 2), ("Client C", 15, 106_000, None),
            ("Client D", 70, 96_000, 0), ("Client D", 40, 99_000, 1),
        ],
        "phantom_paid": [],
        "duplicate_txn": False,
        "rent": 35_000, "payroll": 70_000, "emi": 20_000, "gst": 15_000,
        "daily_spend_scale": 0.8,
    },
}


def build(name: str, spec: dict, seed: int = 7):
    rng = random.Random(seed)
    txns = []  # (date, amount, description, category, counterparty)
    invoices = []

    for i, (cust, issued_ago, amount, delay) in enumerate(spec["invoices"], start=1):
        issue = _d(issued_ago)
        due = issue + timedelta(days=30)
        inv_id = f"INV-{1000 + i}"
        if delay is None:
            invoices.append([inv_id, cust, issue, due, amount, "open", None])
        else:
            paid = due + timedelta(days=delay)
            assert paid <= AS_OF, f"{inv_id} paid in the future"
            invoices.append([inv_id, cust, issue, due, amount, "paid", paid])
            if paid >= START:
                txns.append((paid, amount, f"NEFT from {cust} ({inv_id})", "sales", cust))

    base = 2000 + len(spec["invoices"])
    for j, (cust, issued_ago, amount, delay) in enumerate(spec["phantom_paid"], start=1):
        issue = _d(issued_ago)
        due = issue + timedelta(days=30)
        invoices.append([f"INV-{base + j}", cust, issue, due, amount, "paid", due + timedelta(days=delay)])

    # Fixed monthly outflows that actually happened in the window
    for d in (START + timedelta(days=k) for k in range(DAYS)):
        if d.day == 1:
            txns.append((d, -spec["rent"], "Office rent", "rent", "Landlord"))
        if d.day == 28:
            txns.append((d, -spec["payroll"], "Salary payout", "payroll", "Payroll"))
        if d.day == 12:
            txns.append((d, -spec["emi"], "Loan EMI", "loan_emi", "HDFC Bank"))
        if d.day == 20:
            txns.append((d, -spec["gst"], "GST payment", "tax", "GST Portal"))

    # Variable daily expenses
    seen = set()
    for k in range(DAYS):
        d = START + timedelta(days=k)
        if d.weekday() == 6:
            continue
        for _ in range(rng.choice([1, 1, 2])):
            cat, desc, vendors, (lo, hi) = rng.choice(VARIABLE_EXPENSES)
            amt = round(rng.uniform(lo, hi) * spec["daily_spend_scale"], -1)
            vendor = rng.choice(vendors)
            while (vendor, amt) in seen:      # no accidental duplicates; the planted one is added later
                amt += 10
            seen.add((vendor, amt))
            txns.append((d, -amt, desc, cat, vendor))

    txns.sort(key=lambda t: t[0])

    if spec["duplicate_txn"]:
        dup_idx = next(i for i, t in enumerate(txns) if t[4] == "Sri Traders" and t[0] > START + timedelta(days=40))
        dup = txns[dup_idx]
        txns.insert(dup_idx + 1, (dup[0] + timedelta(days=1), dup[1], dup[2], dup[3], dup[4]))

    # Running balance ending at the target
    total = sum(t[1] for t in txns)
    balance = spec["target_end_balance"] - total
    rows = []
    for n, (d, amt, desc, cat, cp) in enumerate(txns, start=1):
        balance += amt
        rows.append([f"TXN-{n:04d}", d, amt, balance, desc, cat, cp])

    transactions = pd.DataFrame(
        rows, columns=["txn_id", "date", "amount", "balance", "description", "category", "counterparty"])
    invoices = pd.DataFrame(
        invoices, columns=["invoice_id", "customer", "issue_date", "due_date", "amount", "status", "paid_date"])

    def nxt(day, month_offset=0):
        y, m = AS_OF.year, AS_OF.month + month_offset
        if m > 12:
            y, m = y + 1, m - 12
        return date(y, m, day)

    def next_occurrence(day):
        d = nxt(day)
        return d if d > AS_OF else nxt(day, 1)

    obligations = pd.DataFrame([
        ["Office rent", "rent", spec["rent"], next_occurrence(1), "monthly"],
        ["Salaries", "payroll", spec["payroll"], next_occurrence(28), "monthly"],
        ["Business loan EMI", "emi", spec["emi"], next_occurrence(12), "monthly"],
        ["GST", "tax", spec["gst"], next_occurrence(20), "monthly"],
    ], columns=["name", "type", "amount", "next_due_date", "frequency"])

    return transactions, invoices, obligations


def main():
    for name, spec in SCENARIOS.items():
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        t, i, o = build(name, spec)
        t.to_csv(folder / "transactions.csv", index=False, date_format="%Y-%m-%d")
        i.to_csv(folder / "invoices.csv", index=False, date_format="%Y-%m-%d")
        o.to_csv(folder / "obligations.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name}: {len(t)} transactions, {len(i)} invoices, {len(o)} obligations "
              f"-> {folder}  (end balance {t['balance'].iloc[-1]:,.0f})")


if __name__ == "__main__":
    main()