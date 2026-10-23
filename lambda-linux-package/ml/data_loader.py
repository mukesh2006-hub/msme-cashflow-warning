"""
Load and validate the three contract CSVs for one MSME.

    from ml.data_loader import load_all
    data = load_all("data/msme_stressed")
    data["transactions"], data["invoices"], data["obligations"]   # cleaned DataFrames

Works on any local folder, so the Lambda can point it at /tmp/<msme_id>/ after
downloading from S3.
"""
from pathlib import Path

import pandas as pd

from .schema import TABLES, SchemaError, validate


def load_table(data_dir, name: str) -> pd.DataFrame:
    path = Path(data_dir) / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {name}.csv in {data_dir}")
    df = validate(name, pd.read_csv(path))
    if df.empty:
        raise SchemaError(f"{name}.csv has no rows")
    bad_dates = [c for c in TABLES[name]["dates"] if c != "paid_date" and df[c].isna().any()]
    if bad_dates:
        raise SchemaError(f"{name}.csv: unparseable or empty dates in {bad_dates}")
    return df


def load_all(data_dir) -> dict:
    data = {name: load_table(data_dir, name) for name in TABLES}
    data["transactions"] = data["transactions"].sort_values(["date", "txn_id"]).reset_index(drop=True)
    return data