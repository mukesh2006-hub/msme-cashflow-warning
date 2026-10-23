Data Dictionary

1. Purpose

This document describes the CSV input files used by the MSME Cash Flow Warning System. Column names and ordering must follow the team contract and "ml/schema.py" once that file is available.

All monetary amounts are in Indian rupees (INR). Dates use "YYYY-MM-DD".

2. Transactions — "transactions.csv"

Path: "data/<msme_id>/transactions.csv"

Column| Meaning| Rules
"txn_id"| Transaction identifier| Duplicate IDs are intentionally included in the demo data
"date"| Transaction date| "YYYY-MM-DD"
"amount"| Transaction amount| Positive = credit; negative = debit
"balance"| Running account balance after the transaction| Must reconcile with the previous balance and transaction amount
"description"| Transaction description| Text
"category"| Transaction category| Text
"counterparty"| Other party in the transaction| Text

3. Invoices — "invoices.csv"

Path: "data/<msme_id>/invoices.csv"

Column| Meaning| Rules
"invoice_id"| Invoice identifier| Unique invoice reference
"customer"| Customer name| Text
"issue_date"| Invoice issue date| "YYYY-MM-DD"
"due_date"| Payment due date| "YYYY-MM-DD"
"amount"| Invoice amount| INR
"status"| Payment status| "open" or "paid"
"paid_date"| Date payment was recorded| Empty for open invoices

The demo must contain two invoices marked "paid" without corresponding bank credits. These are deliberate data-integrity test cases.

4. Obligations — "obligations.csv"

Path: "data/<msme_id>/obligations.csv"

Column| Meaning| Rules
"name"| Obligation name| Text
"type"| Obligation category| "emi", "rent", "payroll", "tax", or "other"
"amount"| Amount payable| INR
"next_due_date"| Next payment date| "YYYY-MM-DD"
"frequency"| Payment frequency| "monthly", "weekly", or "once"

5. Demo datasets

- "msme_healthy": example business with comparatively stronger liquidity.
- "msme_stressed": example business with late-paying customers, an EMI due within 30 days, and an intentionally duplicated transaction.

6. Storage layout

Local files:

"data/<msme_id>/<file>.csv"

Amazon S3 objects:

"s3://<bucket>/<msme_id>/<file>.csv"

The schema must be checked against "ml/schema.py" before integration.