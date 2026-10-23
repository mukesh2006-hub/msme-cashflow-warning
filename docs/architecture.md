MSME Cash Flow Warning System — Architecture

1. Purpose

The MSME Cash Flow Warning System forecasts cash flow and identifies potential liquidity risks for micro, small, and medium enterprises.

2. Components and responsibilities

- Person A — Data and AWS: Prepares the MSME CSV datasets, stores them in Amazon S3, implements the AWS Lambda integration, and maintains project documentation.
- Person B — Machine Learning: Implements "ml.run_analysis()" and returns the agreed JSON-serialisable analysis dictionary.
- Person C — UI and Demo: Displays the analysis results, including the cash forecast, financial health score, liquidity gaps, and warnings.

3. Input data

Each MSME has three input files:

- "transactions.csv"
- "invoices.csv"
- "obligations.csv"

Local layout:

"data/<msme_id>/<file>.csv"

S3 layout:

"s3://<bucket>/<msme_id>/<file>.csv"

Demo MSME IDs:

- "msme_healthy"
- "msme_stressed"

The CSV schema must follow the team's "CONTRACT.md" and "ml/schema.py" once available.

4. Analysis flow

1. The input CSV files are prepared and validated.
2. The CSV files are uploaded to the designated S3 bucket.
3. AWS Lambda receives an MSME ID.
4. Lambda downloads the three CSV files into "/tmp/<msme_id>/".
5. Lambda invokes "ml.run_analysis()" on that directory.
6. The returned result is serialised as JSON.
7. Lambda writes the result to "s3://<bucket>/<msme_id>/analysis.json".
8. The UI consumes the analysis result according to the agreed output contract.

5. Machine-learning interface

Local invocation:

"run_analysis("data/msme_stressed")"

What-if loan invocation:

"run_analysis("data/msme_stressed", loan_amount=500000)"

The returned dictionary must preserve the agreed output keys and data types.

6. Security and reliability

- Keep the S3 bucket private.
- Grant Lambda only the permissions it requires.
- Store AWS credentials outside the source code.
- Validate input files before analysis.
- Record errors without exposing sensitive financial data.
- Coordinate interface changes with both teammates before implementation.

7. Integration status

This document describes the planned architecture. AWS resources, Lambda deployment, and end-to-end integration must be marked complete only after they have been tested.