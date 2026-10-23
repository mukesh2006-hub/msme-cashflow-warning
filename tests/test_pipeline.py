"""
Guard rails for the two demo scenarios. Run from the repo root:

    python -m pytest ml/tests -q

If a test fails after you tune config.py or the test data, either the change broke the
demo story (fix it) or the story changed on purpose (update the assertion).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml import config, run_analysis                      # noqa: E402
from ml.data_loader import load_all                      # noqa: E402
from ml.features import compute_features                 # noqa: E402
from ml.reconcile import reconcile                       # noqa: E402

STRESSED = str(ROOT / "data" / "msme_stressed")
HEALTHY = str(ROOT / "data" / "msme_healthy")


@pytest.fixture(scope="module")
def stressed():
    return run_analysis(STRESSED)


@pytest.fixture(scope="module")
def healthy():
    return run_analysis(HEALTHY)


# ---------- reconciliation ----------
def test_reconcile_flags_planted_paid_invoices():
    rec = reconcile(load_all(STRESSED))
    assert set(rec["unmatched_paid"]["invoice_id"]) == {"INV-2013", "INV-2014"}


def test_reconcile_clean_on_healthy():
    assert reconcile(load_all(HEALTHY))["unmatched_paid"].empty


def test_client_x_is_the_late_payer():
    cd = reconcile(load_all(STRESSED))["customer_delays"].set_index("customer")["avg_delay_days"]
    assert cd["Client X"] > 30
    assert cd["Client Y"] < 5


# ---------- features ----------
def test_stressed_features():
    d = load_all(STRESSED)
    f = compute_features(d, reconcile(d))
    assert f["late_share"] >= 0.3
    assert f["metrics"]["dscr"] < 1
    assert f["metrics"]["cash_buffer_days"] < config.MIN_CASH_BUFFER_DAYS
    assert f["top_customer"] == "Client X"


def test_healthy_features():
    d = load_all(HEALTHY)
    f = compute_features(d, reconcile(d))
    assert f["late_share"] == 0
    assert f["metrics"]["dscr"] > 1.5
    assert f["metrics"]["cash_buffer_days"] > config.MIN_CASH_BUFFER_DAYS


# ---------- the demo story ----------
def test_stressed_story(stressed):
    assert stressed["gap"]["has_gap"] is True
    assert stressed["gap"]["gap_amount"] > 0
    assert stressed["summary"]["risk_level"] == "At risk"
    assert stressed["summary"]["health_score"] < 50
    assert {"liquidity_gap", "repayment_risk", "receivable_risk", "data_integrity"} <= {w["type"] for w in stressed["warnings"]}
    assert stressed["safe_loan_amount"] == 0
    assert any(a["type"] == "paid_no_credit" for a in stressed["anomalies"])
    assert any(a["type"] == "duplicate" for a in stressed["anomalies"])


def test_healthy_story(healthy):
    assert healthy["gap"]["has_gap"] is False
    assert healthy["summary"]["risk_level"] == "Healthy"
    assert healthy["summary"]["health_score"] >= 75
    assert healthy["warnings"] == []
    assert healthy["anomalies"] == []
    assert healthy["safe_loan_amount"] > 0


# ---------- forecast shape ----------
def test_forecast_shape(stressed):
    fc = stressed["forecast"]
    n = config.FORECAST_HORIZON_DAYS
    assert all(len(fc[k]) == n for k in ("dates", "balance", "lower", "upper", "inflows", "outflows"))
    assert all(lo <= up for lo, up in zip(fc["lower"], fc["upper"]))
    assert fc["dates"] == sorted(fc["dates"])


# ---------- score ----------
def test_score_is_consistent(stressed, healthy):
    assert abs(sum(config.SCORE_WEIGHTS.values()) - 1) < 1e-9
    for r in (stressed, healthy):
        subs = r["score"]["sub_scores"]
        assert set(subs) == set(config.SCORE_WEIGHTS)
        assert all(0 <= s["score"] <= 100 and s["detail"] for s in subs.values())
        expected = sum(s["score"] * s["weight"] for s in subs.values())
        assert abs(r["score"]["total"] - expected) <= 1       # rounding only
        assert r["summary"]["health_score"] == r["score"]["total"]


# ---------- contract with C and A ----------
def test_output_matches_contract(stressed, healthy):
    mock = run_analysis(STRESSED, use_mock=True)
    for r in (stressed, healthy):
        for key, val in mock.items():
            assert key in r, f"missing top-level key {key}"
            if isinstance(val, dict):
                missing = [k for k in val if k not in r[key]]
                assert not missing, f"{key} is missing {missing}"
        json.dumps(r)                                          # must be JSON-serialisable


def test_deterministic():
    assert run_analysis(STRESSED) == run_analysis(STRESSED)


# ---------- what-if loan ----------
def test_loan_lowers_dscr():
    base = run_analysis(HEALTHY)["metrics"]["dscr"]
    with_loan = run_analysis(HEALTHY, loan_amount=500_000)["metrics"]["dscr"]
    assert with_loan < base


def test_missing_file_gives_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_analysis(str(tmp_path))