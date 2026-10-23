
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from ml import run_analysis

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

app = Flask(__name__)

# Allow the frontend running through VS Code Live Server.
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://127.0.0.1:5500",
                "http://localhost:5500",
                "http://127.0.0.1:5501",
                "http://localhost:5501",
            ]
        }
    },
)

# Limit each uploaded file to 10 MB.
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


@app.get("/api/health")
def health():
    print("HEALTH ENDPOINT WAS CALLED", flush=True)
    return jsonify({
        "status": "ok",
        "service": "MSME Cash-Flow Warning API",
    
    })




@app.post("/api/analyze")
def analyze():
    """
    Accept three CSV files:
    transactions, invoices, and obligations.
    """
    required = [
        "transactions",
        "invoices",
        "obligations",
    ]

    missing = [
        name for name in required
        if name not in request.files
        or not request.files[name].filename
    ]

    if missing:
        return jsonify({
            "error": (
                "Upload all three CSV files. Missing: "
                + ", ".join(missing)
            )
        }), 400

    loan_amount = None
    raw_loan = request.form.get("loan_amount", "").strip()

    if raw_loan:
        try:
            loan_amount = float(raw_loan)
            if not 0 <= loan_amount <= 100_000_000:
                raise ValueError()
        except ValueError:
            return jsonify({
                "error": "loan_amount must be between 0 and 100000000."
            }), 400

        if loan_amount == 0:
            loan_amount = None

    try:
        # Use a temporary directory instead of accepting arbitrary paths.
        with tempfile.TemporaryDirectory(prefix="msme_") as temp:
            for name in required:
                uploaded = request.files[name]

                if not uploaded.filename.lower().endswith(".csv"):
                    return jsonify({
                        "error": f"{name} must be a CSV file."
                    }), 400

                destination = Path(temp) / f"{name}.csv"
                uploaded.save(destination)

            result = run_analysis(
                temp,
                loan_amount=loan_amount,
            )

        return jsonify(result)

    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Financial analysis failed")
        return jsonify({
            "error": "Analysis failed. Check the backend terminal."
        }), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
