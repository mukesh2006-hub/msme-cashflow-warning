"""All tunable numbers live here. Change demo behaviour from this one file."""

FORECAST_HORIZON_DAYS = 30
MIN_CASH_BUFFER_DAYS = 15          # buffer below this triggers a liquidity warning
LATE_THRESHOLD_DAYS = 30           # invoice counts as "late" when 30 or more days overdue
BASELINE_WINDOW_DAYS = 60          # lookback for variable-expense moving average
MONTE_CARLO_RUNS = 500             # used later for confidence bands
CONCENTRATION_LIMIT = 0.40         # top customer share above this is flagged
DUPLICATE_WINDOW_DAYS = 3

# Health score: weights must sum to 1.0
SCORE_WEIGHTS = {
    "liquidity": 0.30,
    "collections": 0.25,
    "debt_servicing": 0.25,
    "data_consistency": 0.10,
    "stability": 0.10,
}

# Score bands (inclusive lower bound)
SCORE_BANDS = [(75, "Healthy"), (50, "Watch"), (0, "At risk")]

# Aging buckets in days overdue
AGING_BUCKETS = ["0-30", "31-60", "61-90", "90+"]

assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9, "SCORE_WEIGHTS must sum to 1"

# Reconciliation (invoice <-> bank credit matching)
RECON_AMOUNT_TOLERANCE = 0.01      # credit may differ from invoice by up to 1%
RECON_DATE_WINDOW_DAYS = 5         # credit must land within +/- this many days of paid_date

# Features
LOOKBACK_DAYS = 90                 # window for revenue, spend and DSO calculations

# Forecast
OVERDUE_CATCHUP_DAYS = 20          # invoice already later than the customer's usual delay is a riskier payer: assume it lands this many days from now
MIN_DELAY_STD_DAYS = 3.0           # floor on a customer's payment-delay spread in Monte Carlo
VARIABLE_SPEND_NOISE = 0.15        # +/- spread on daily variable spend in Monte Carlo
MC_SEED = 42                       # fixed so the demo gives identical numbers every run
WHATIF_LOAN_RATE = 0.12            # annual rate used for the what-if loan EMI
WHATIF_LOAN_TENOR_MONTHS = 36

# Health score thresholds: (worst value -> 0 points, best value -> 100 points), linear in between
GOOD_BUFFER_DAYS = 30              # cash buffer at/above this scores 100 on the buffer part
LATE_SHARE_RANGE = (0.40, 0.0)     # share of receivables 30+ days late
OVERDUE_SHARE_RANGE = (0.80, 0.0)  # share of receivables past due at all
AVG_DELAY_RANGE = (30.0, 0.0)      # average payment delay, days
DSCR_RANGE = (0.8, 1.5)            # debt service coverage ratio
INFLOW_CV_RANGE = (1.2, 0.3)       # weekly-inflow volatility (std / mean)
CONCENTRATION_RANGE = (0.60, 0.25) # top-customer share of revenue
ANOMALY_PENALTY = {"high": 25, "medium": 12, "low": 6}   # points off data_consistency per flag

# Safe-loan calculator
SAFE_LOAN_MIN_DSCR = 1.2                 # keep DSCR at or above this after the new EMI
SAFE_LOAN_MAX_MONTHS_OF_INFLOW = 6       # never suggest more than this many months of inflow