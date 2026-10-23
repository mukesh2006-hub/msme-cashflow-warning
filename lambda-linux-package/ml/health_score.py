"""
Transparent 0-100 financial-health score built from five weighted sub-scores.
Every sub-score carries a plain-language `detail` so the score can be explained.

    from ml.health_score import compute_score
    score = compute_score(feats, gap, rec)            # matches the "score" block of the contract
    score = compute_score(feats, gap, rec, anomalies) # once anomalies.py exists
"""
from . import config


def _scale(x, worst, best) -> float:
    """Linear map: worst -> 0, best -> 100, clipped. Works whichever way round the range is."""
    if x is None:
        return 100.0
    pts = (x - worst) / (best - worst) * 100
    return max(0.0, min(100.0, pts))


def _pct(x) -> str:
    return f"{x * 100:.0f}%"


def compute_score(feats: dict, gap: dict, rec: dict, anomalies=None) -> dict:
    m = feats["metrics"]
    sub = {}

    # 1) Liquidity: how many days cash lasts + chance of running dry
    buffer_pts = _scale(m["cash_buffer_days"], 0, config.GOOD_BUFFER_DAYS)
    gap_pts = 100 * (1 - gap["prob_gap"])
    sub["liquidity"] = (
        0.6 * buffer_pts + 0.4 * gap_pts,
        f"Cash covers {m['cash_buffer_days']:.0f} day(s) of expenses; "
        f"{_pct(gap['prob_gap'])} chance of going negative in the next {config.FORECAST_HORIZON_DAYS} days",
    )

    # 2) Collections: how much is late and how slowly customers pay
    pts = (0.5 * _scale(feats["late_share"], *config.LATE_SHARE_RANGE)
           + 0.3 * _scale(feats["overdue_share"], *config.OVERDUE_SHARE_RANGE)
           + 0.2 * _scale(m["avg_payment_delay_days"], *config.AVG_DELAY_RANGE))
    sub["collections"] = (
        pts,
        f"{_pct(feats['late_share'])} of receivables are {config.LATE_THRESHOLD_DAYS}+ days late; "
        f"{_pct(feats['overdue_share'])} are past due; customers pay {m['avg_payment_delay_days']:.0f} days late on average",
    )

    # 3) Debt servicing: can operating cash cover the EMI?
    if m["dscr"] is None:
        sub["debt_servicing"] = (100.0, "No recurring loan repayments")
    else:
        sub["debt_servicing"] = (
            _scale(m["dscr"], *config.DSCR_RANGE),
            f"DSCR {m['dscr']:.2f} (target {config.DSCR_RANGE[1]}+)",
        )

    # 4) Data consistency: penalty per data-integrity flag
    if anomalies is None:   # fall back to reconciliation result until anomalies.py exists
        anomalies = [{"severity": "high", "type": "paid_no_credit"} for _ in range(len(rec["unmatched_paid"]))]
    penalty = sum(config.ANOMALY_PENALTY.get(a["severity"], 0) for a in anomalies)
    sub["data_consistency"] = (
        max(0.0, 100 - penalty),
        f"{len(anomalies)} data-integrity flag(s)" if anomalies else "No inconsistencies found",
    )

    # 5) Stability: lumpy income and dependence on one customer
    pts = (0.6 * _scale(feats["inflow_cv"], *config.INFLOW_CV_RANGE)
           + 0.4 * _scale(m["top_customer_share"], *config.CONCENTRATION_RANGE))
    sub["stability"] = (
        pts,
        f"Weekly income volatility {feats['inflow_cv']:.2f}; top customer is {_pct(m['top_customer_share'])} of revenue",
    )

    total = sum(config.SCORE_WEIGHTS[k] * v[0] for k, v in sub.items())
    band = next(name for floor, name in config.SCORE_BANDS if total >= floor)
    return {
        "total": round(total),
        "band": band,
        "sub_scores": {
            k: {"score": round(v[0]), "weight": config.SCORE_WEIGHTS[k], "detail": v[1]}
            for k, v in sub.items()
        },
    }