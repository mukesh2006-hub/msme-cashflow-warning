Demo Runbook

1. Purpose

Demonstrate how the MSME Cash Flow Warning System distinguishes a comparatively healthy business from a financially stressed business.

2. Demo scenarios

Scenario A: "msme_healthy"

1. Select the "msme_healthy" dataset.
2. Run the analysis through the agreed ML interface.
3. Review the current balance, forecast, health score, and warnings.
4. Explain the results using the returned analysis fields.

Scenario B: "msme_stressed"

1. Select the "msme_stressed" dataset.
2. Run the analysis through the agreed ML interface.
3. Review the forecast and any projected liquidity gap.
4. Review late invoices and the EMI due within 30 days.
5. Demonstrate the duplicate transaction and paid-invoice-without-credit anomalies if reported by the pipeline.

3. Local ML invocation

When Person B's ML interface is available:

from ml import run_analysis

result = run_analysis("data/msme_stressed")

Optional what-if loan analysis:

result = run_analysis(
    "data/msme_stressed",
    loan_amount=500000
)

4. AWS demonstration

Once Lambda is deployed and tested:

1. Upload the input CSV files to S3.
2. Invoke the Lambda function for the selected MSME ID.
3. Confirm the corresponding "analysis.json" is written to S3.
4. Load the output in the UI when Person C's integration is ready.

5. Expected output

The output should follow the agreed contract, including summary, forecast, gap, score, receivables aging, metrics, explanations, anomalies, warnings, and safe loan amount.

Actual values must come from the tested analysis result. Do not promise a particular score or forecast until the pipeline has been run.

6. Troubleshooting

- Missing CSV: verify the local path or S3 object key.
- Invalid schema: compare columns with the team contract and "ml/schema.py".
- Lambda import error: coordinate ML packaging and dependencies with Person B.
- Missing analysis output: inspect Lambda execution logs and S3 write permissions.
- UI output mismatch: compare the actual JSON with the agreed output contract and coordinate with Person C.

7. Completion checklist

- [ ] Local CSV files validated.
- [ ] Input files uploaded to S3.
- [ ] Lambda execution verified.
- [ ] Analysis JSON verified.
- [ ] UI integration tested.
- [ ] Demo rehearsed.