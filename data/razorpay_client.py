"""
Optional live-data path. If you have real Razorpay API keys, this pulls
failed payments straight from your account and normalizes them into the
same schema as razorpay_demo_payments.csv, so every downstream component
(diagnosis, ML, policy, agent, simulator) runs unchanged.

Usage:
    export RAZORPAY_KEY_ID=rzp_test_xxx
    export RAZORPAY_KEY_SECRET=xxxxxxxx
    python razorpay_client.py --count 100 --from 1690000000 --to 1699999999

Requires: pip install razorpay
"""

import argparse
import csv
import os
import sys
from pathlib import Path

OUT_PATH = Path(__file__).parent / "razorpay_live_payments.csv"

FIELDNAMES = [
    "id", "order_id", "entity", "amount", "currency", "status", "method",
    "captured", "email", "contact", "customer_id", "bank",
    "error_code", "error_description", "error_source", "error_step", "error_reason",
    "root_cause", "created_at", "attempt_number", "previous_success_rate",
    "previous_failure_rate", "upi_success_rate", "card_success_rate",
    "time_since_last_attempt_min", "hour", "day_of_week",
    "checkout_duration_sec", "customer_value_tier", "recovered", "recovery_action",
]

# Same root-cause mapping used by diagnosis/root_cause.py, applied here so
# live rows are diagnosable the moment they're pulled.
from sys import path as _path
_path.append(str(Path(__file__).parent.parent / "agent"))
try:
    from root_cause import classify_root_cause
except ImportError:
    def classify_root_cause(error_reason, error_source, method):
        return "UNKNOWN"


def normalize(payment: dict) -> dict:
    """Map a raw Razorpay payment entity (from payments.all()) to our schema."""
    error_reason = payment.get("error_reason") or ""
    error_source = payment.get("error_source") or ""
    method = payment.get("method") or ""
    root_cause = classify_root_cause(error_reason, error_source, method) if payment.get("status") == "failed" else ""

    import datetime
    ts = payment.get("created_at", 0)
    dt = datetime.datetime.utcfromtimestamp(ts) if ts else None

    return {
        "id": payment.get("id", ""),
        "order_id": payment.get("order_id", ""),
        "entity": payment.get("entity", "payment"),
        "amount": payment.get("amount", 0),
        "currency": payment.get("currency", "INR"),
        "status": payment.get("status", ""),
        "method": method,
        "captured": payment.get("captured", False),
        "email": payment.get("email", ""),
        "contact": payment.get("contact", ""),
        "customer_id": payment.get("customer_id", ""),
        "bank": payment.get("bank") or "",
        "error_code": payment.get("error_code") or "",
        "error_description": payment.get("error_description") or "",
        "error_source": error_source,
        "error_step": payment.get("error_step") or "",
        "error_reason": error_reason,
        "root_cause": root_cause,
        "created_at": ts,
        # These four are NOT in the raw Payment entity - a real integration
        # would join them from your own customer/orders tables. Defaulted
        # here so the schema lines up; wire up real joins before production use.
        "attempt_number": 1,
        "previous_success_rate": 0.5,
        "previous_failure_rate": 0.5,
        "upi_success_rate": 0.5,
        "card_success_rate": 0.5,
        "time_since_last_attempt_min": 0,
        "hour": dt.hour if dt else 0,
        "day_of_week": dt.weekday() if dt else 0,
        "checkout_duration_sec": 0,
        "customer_value_tier": "mid",
        "recovered": "",  # unknown until the agent acts
        "recovery_action": "",
    }


def fetch(count: int, from_ts: int = None, to_ts: int = None):
    try:
        import razorpay
    except ImportError:
        print("Install the SDK first:  pip install razorpay", file=sys.stderr)
        sys.exit(1)

    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        print("Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET env vars.", file=sys.stderr)
        sys.exit(1)

    client = razorpay.Client(auth=(key_id, key_secret))
    params = {"count": min(count, 100)}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    resp = client.payment.all(params)
    payments = [p for p in resp.get("items", []) if p.get("status") == "failed"]
    rows = [normalize(p) for p in payments]

    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} failed payments to {OUT_PATH}")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--from", dest="from_ts", type=int, default=None)
    ap.add_argument("--to", dest="to_ts", type=int, default=None)
    args = ap.parse_args()
    fetch(args.count, args.from_ts, args.to_ts)
