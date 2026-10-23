import json
import os
import boto3
from pathlib import Path
from urllib.parse import unquote_plus

from ml import run_analysis

s3 = boto3.client("s3")

BUCKET_NAME = "msme-cashflow-demo-mukesh-2026"
INPUT_PREFIX = "msme_stressed/"
OUTPUT_PREFIX = "results/"


def lambda_handler(event, context):
    # Allow a manual test event to specify a dataset prefix.
    prefix = event.get("prefix", INPUT_PREFIX)

    if not prefix.endswith("/"):
        prefix += "/"

    # Download the three CSV files into Lambda's temporary folder.
    local_dir = Path("/tmp/msme_stressed")
    local_dir.mkdir(parents=True, exist_ok=True)

    required_files = [
        "transactions.csv",
        "invoices.csv",
        "obligations.csv",
    ]

    for filename in required_files:
        local_path = local_dir / filename
        s3.download_file(
            BUCKET_NAME,
            f"{prefix}{filename}",
            str(local_path),
        )

    # Run the ML pipeline on the downloaded dataset.
    result = run_analysis(str(local_dir))

    # Save results outside the input prefix to avoid recursive triggers.
    result_key = f"{OUTPUT_PREFIX}analysis.json"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=result_key,
        Body=json.dumps(result, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "MSME analysis completed",
            "result_location": f"s3://{BUCKET_NAME}/{result_key}",
            "msme_id": result.get("msme_id"),
            "summary": result.get("summary"),
        }, default=str),
    }