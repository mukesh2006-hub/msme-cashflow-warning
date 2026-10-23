"""
Data contract between A (data/AWS) and B (ML).
A produces CSVs with exactly these columns. B validates against them.

Folder layout (local) / key layout (S3) per MSME:
    data/<msme_id>/transactions.csv
    data/<msme_id>/invoices.csv
    data/<msme_id>/obligations.csv
"""
import pandas as pd

TABLES = {
    # One row per bank transaction. amount > 0 = credit (money in), < 0 = debit.
    "transactions": {
        "required": ["txn_id", "date", "amount", "balance", "description", "category", "counterparty"],
        "dates": ["date"],
        "numeric": ["amount", "balance"],
    },
    # One row per invoice issued to a customer (receivables).
    # status: "open" or "paid". paid_date is empty while open.
    "invoices": {
        "required": ["invoice_id", "customer", "issue_date", "due_date", "amount", "status", "paid_date"],
        "dates": ["issue_date", "due_date", "paid_date"],
        "numeric": ["amount"],
    },
    # Known recurring/one-off outflows: EMI, rent, payroll, tax.
    # type: emi | rent | payroll | tax | other
    # frequency: monthly | weekly | once
    "obligations": {
        "required": ["name", "type", "amount", "next_due_date", "frequency"],
        "dates": ["next_due_date"],
        "numeric": ["amount"],
    },
}

ALLOWED_VALUES = {
    "invoices.status": {"open", "paid"},
    "obligations.type": {"emi", "rent", "payroll", "tax", "other"},
    "obligations.frequency": {"monthly", "weekly", "once"},
}


class SchemaError(ValueError):
    pass


def validate(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Check columns, parse dates/numbers, check allowed values. Returns cleaned df."""
    spec = TABLES[name]
    missing = [c for c in spec["required"] if c not in df.columns]
    if missing:
        raise SchemaError(f"{name}: missing columns {missing}")

    df = df[spec["required"]].copy()
    for c in spec["dates"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in spec["numeric"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for key, allowed in ALLOWED_VALUES.items():
        tbl, col = key.split(".")
        if tbl == name:
            bad = set(df[col].dropna().str.lower()) - allowed
            if bad:
                raise SchemaError(f"{name}.{col}: unexpected values {bad}")
            df[col] = df[col].str.lower()

    return df