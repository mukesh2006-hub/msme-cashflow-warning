AWS Setup Guide

1. Status

This guide describes the planned setup. Mark each step complete only after verifying it in the AWS console or through a test.

2. S3 bucket

1. Create a dedicated S3 bucket in the selected AWS Region.
2. Keep Block Public Access enabled.
3. Use the same bucket for the input CSVs and analysis output unless the team agrees otherwise.
4. Upload each MSME's three CSV files using the agreed object keys.

Required input keys:

- "<msme_id>/transactions.csv"
- "<msme_id>/invoices.csv"
- "<msme_id>/obligations.csv"

Required output key:

- "<msme_id>/analysis.json"

3. Lambda function

The Lambda function must:

1. Receive or determine the MSME ID.
2. Download the three CSV objects into "/tmp/<msme_id>/".
3. Invoke "run_analysis()" from the ML package.
4. Serialise the returned dictionary as JSON.
5. Upload the JSON to "<msme_id>/analysis.json".

The ML package and its dependencies must be packaged or deployed in a supported Lambda configuration. Coordinate packaging with Person B.

4. IAM permissions

Use a dedicated Lambda execution role.

Grant only the permissions needed to read the three input objects and write the analysis output. Restrict access to the designated bucket and relevant object paths where practical.

Do not commit AWS access keys, passwords, or other secrets to Git.

5. Configuration

Document the following when deployment details are decided:

- AWS Region
- S3 bucket name
- Lambda function name
- Runtime and dependency packaging method
- Input and output object paths
- Required environment variables

Do not store secret values in this document.

6. Verification

Before integration is considered complete:

- Confirm the three input files exist in S3 for each demo MSME.
- Invoke Lambda with "msme_healthy".
- Invoke Lambda with "msme_stressed".
- Confirm each invocation produces valid JSON at "<msme_id>/analysis.json".
- Check logs for errors without exposing sensitive financial data.
- Confirm the output keys match the team's agreed ML contract.