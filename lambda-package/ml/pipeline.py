"""
Single entry point for ML.  Members A (Lambda) and C (Streamlit) call ONLY this:

    from ml import run_analysis
    result = run_analysis("data/msme_stressed")
    result = run_analysis("data/msme_stressed", loan_amount=500000)   # what-if loan
    result = run_analysis("data/msme_stressed", use_mock=True)        # fixed fake result for UI work

The returned dict is the contract (see docs/CONTRACT.md). Everything is
JSON-serialisable (dates as ISO strings, no DataFrames) so it can pass through
API Gateway / S3 unchanged.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from . import config
from .anomalies import INTEGRITY_TYPES, find_anomalies
from .data_loader import load_all
from .explain import build_explanations, build_warnings, safe_loan_amount
from .features import compute_features
from .forecast import forecast_cash
from .gap_detection import detect_gap
from .health_score import compute_score
from .reconcile import reconcile
from .utils import emi

USE_MOCK = False


def _apply_loan(feats: dict, loan_amount: float) -> None:
    """What-if: add the new loan's EMI to repayments and recompute DSCR."""
    feats["monthly_emi"] += emi(loan_amount, config.WHATIF_LOAN_RATE, config.WHATIF_LOAN_TENOR_MONTHS)
    surplus = feats["monthly_inflow"] - feats["monthly_opex"]
    feats["metrics"]["dscr"] = round(surplus / feats["monthly_emi"], 2)


def run_analysis(data_dir: str, as_of: str | None = None, loan_amount: float | None = None,
                 use_mock: bool | None = None) -> dict:
    """
    data_dir    folder containing transactions.csv, invoices.csv, obligations.csv
    as_of       ISO date to treat as "today" (default: latest transaction date)
    loan_amount optional what-if loan; adds its disbursal and EMI before forecasting
    use_mock    True returns the fixed fake result (for UI development)
    """
    msme_id = Path(data_dir).name
    if USE_MOCK if use_mock is None else use_mock:
        return _mock_result(msme_id, as_of)

    data = load_all(data_dir)
    rec = reconcile(data)
    feats = compute_features(data, rec, as_of)
    if loan_amount:
        _apply_loan(feats, loan_amount)
    fc = forecast_cash(data, feats, rec, loan_amount=loan_amount)
    gap = detect_gap(fc, feats, rec)
    anomalies = find_anomalies(data, rec, feats)
    score = compute_score(feats, gap, rec, [a for a in anomalies if a["type"] in INTEGRITY_TYPES])

    return {
        "msme_id": msme_id,
        "as_of": feats["as_of"].strftime("%Y-%m-%d"),
        "currency": "INR",
        "summary": {
            "current_balance": round(feats["current_balance"]),
            "health_score": score["total"],
            "risk_level": score["band"],
        },
        "forecast": {k: fc[k] for k in ("dates", "balance", "lower", "upper", "inflows", "outflows")},
        "gap": gap,
        "score": score,
        "receivables_aging": {k: round(v) for k, v in feats["receivables_aging"].items()},
        "metrics": feats["metrics"],
        "explanations": build_explanations(data, feats, gap, rec, anomalies),
        "anomalies": anomalies,
        "warnings": build_warnings(data, feats, gap, fc, rec, anomalies),
        "safe_loan_amount": safe_loan_amount(feats),
    }


def _mock_result(msme_id: str, as_of: str | None) -> dict:
    today = date.fromisoformat(as_of) if as_of else date(2026, 10, 23)
    days = 30
    dates = [(today + timedelta(days=i)).isoformat() for i in range(days)]
    # Balance slides down and dips negative around day 18 (EMI + late payers)
    balance = [round(250000 - i * 13500 + (40000 if i == 9 else 0), 0) for i in range(days)]
    inflows = [0 if i % 5 else 30000 for i in range(days)]
    outflows = [0 if i % 4 else 28000 for i in range(days)]
    gap_idx = next((i for i, b in enumerate(balance) if b < 0), None)

    return {
        "msme_id": msme_id,
        "as_of": today.isoformat(),
        "currency": "INR",
        "summary": {
            "current_balance": 250000,
            "health_score": 41,
            "risk_level": "At risk",
        },
        "forecast": {
            "dates": dates,
            "balance": balance,
            "lower": [b - 25000 for b in balance],   # confidence band (P10)
            "upper": [b + 25000 for b in balance],   # confidence band (P90)
            "inflows": inflows,
            "outflows": outflows,
        },
        "gap": {
            "has_gap": gap_idx is not None,
            "first_gap_date": dates[gap_idx] if gap_idx is not None else None,
            "min_balance": min(balance),
            "gap_amount": abs(min(min(balance), 0)),
            "causes": [
                "3 invoices from Client X are ~38 days late",
                "EMI of 45,000 due on the 28th",
            ],
        },
        "score": {
            "total": 41,
            "band": "At risk",
            "sub_scores": {
                "liquidity":        {"score": 35, "weight": 0.30, "detail": "Cash covers 9 days of expenses"},
                "collections":      {"score": 30, "weight": 0.25, "detail": "40% of receivables are 30+ days late"},
                "debt_servicing":   {"score": 45, "weight": 0.25, "detail": "DSCR 1.1 (target 1.5)"},
                "data_consistency": {"score": 70, "weight": 0.10, "detail": "2 invoices marked paid with no bank credit"},
                "stability":        {"score": 55, "weight": 0.10, "detail": "Moderate income volatility"},
            },
        },
        "receivables_aging": {"0-30": 120000, "31-60": 90000, "61-90": 60000, "90+": 20000},
        "metrics": {
            "dso_days": 52,
            "top_customer_share": 0.46,
            "cash_buffer_days": 9,
            "dscr": 1.1,
            "avg_payment_delay_days": 24,
        },
        "explanations": [
            {"severity": "high", "title": "Collections are slow",
             "message": "Score dropped because 40% of receivables are 30+ days late.",
             "metric": "late_receivables_share", "value": 0.40},
            {"severity": "medium", "title": "Customer concentration",
             "message": "46% of revenue comes from one customer.",
             "metric": "top_customer_share", "value": 0.46},
        ],
        "anomalies": [
            {"type": "paid_no_credit", "severity": "high", "ref_id": "INV-1042",
             "message": "Invoice marked paid but no matching bank credit found."},
            {"type": "duplicate", "severity": "low", "ref_id": "TXN-5521",
             "message": "Possible duplicate transaction within 3 days."},
        ],
        "warnings": [
            {"type": "liquidity_gap", "severity": "high", "date": dates[gap_idx] if gap_idx is not None else None,
             "message": "Cash is projected to go negative.",
             "action": "Chase the 3 late invoices from Client X before the EMI date."},
            {"type": "repayment_risk", "severity": "medium", "date": dates[min(days - 1, 25)],
             "message": "EMI due with thin cash buffer.",
             "action": "Negotiate EMI date or reduce loan amount."},
        ],
        "safe_loan_amount": 150000,
    }