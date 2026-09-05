"""
Builds `razorpay_demo_payments.csv`.

Every categorical value used here (error codes, error reasons, error
sources, error steps, payment methods, bank codes) is copied from
Razorpay's own public API documentation - see README.md for the exact
pages. This script does not invent a schema; it recombines Razorpay's
documented Payment-entity and Error-entity vocabulary into transaction
rows, with a `recovered` / `recovery_action` outcome label attached so
the rest of the pipeline (diagnosis -> ML -> policy -> agent ->
simulator) has something concrete to run against.

Run: python build_demo_dataset.py
"""

import csv
import random
import time
from pathlib import Path

random.seed(42)  # reproducible fixture, not a live random stream

OUT_PATH = Path(__file__).parent / "razorpay_demo_payments.csv"
N_ROWS = 1200

# ---------------------------------------------------------------------------
# Vocabulary taken directly from Razorpay's documented Payment/Error schema
# https://razorpay.com/docs/api/payments/entity/
# https://razorpay.com/docs/payments/payment-gateway/rainy-day/errors/error-codes
# ---------------------------------------------------------------------------

METHODS = ["card", "upi", "netbanking", "wallet", "emi"]

# (error_code, error_source, error_step, error_reason, error_description, root_cause_bucket)
FAILURE_TEMPLATES = [
    ("GATEWAY_ERROR", "gateway", "payment_authorization", "payment_declined",
     "Payment was declined by the issuing bank/gateway.", "BANK_DECLINE"),
    ("GATEWAY_ERROR", "bank", "payment_authorization", "bank_server_error",
     "Payment failed due to a temporary issue at the bank's end.", "NETWORK_TIMEOUT"),
    ("GATEWAY_ERROR", "gateway", "payment_processing", "gateway_timeout",
     "Payment was unsuccessful due to a temporary issue.", "NETWORK_TIMEOUT"),
    ("BAD_REQUEST_ERROR", "customer", "payment_authentication", "incorrect_otp",
     "Authentication failed due to incorrect otp.", "USER_ABANDONMENT"),
    ("BAD_REQUEST_ERROR", "customer", "payment_authentication", "otp_timeout",
     "Customer did not complete OTP authentication in time.", "USER_ABANDONMENT"),
    ("GATEWAY_ERROR", "customer", "payment_authorization", "insufficient_funds",
     "Payment failed because of insufficient funds in the account.", "CARD_FAILURE"),
    ("GATEWAY_ERROR", "customer", "payment_authorization", "card_expired",
     "The card used for payment has expired.", "CARD_FAILURE"),
    ("GATEWAY_ERROR", "business", "payment_authorization", "risk_check_failed",
     "Payment was flagged and declined by risk checks.", "RETRY_LIMIT"),
    ("SERVER_ERROR", "gateway", "payment_processing", "internal_error",
     "The service was temporarily unavailable.", "NETWORK_TIMEOUT"),
    ("GATEWAY_ERROR", "bank", "payment_authorization", "upi_declined",
     "UPI payment was declined by the customer's bank/PSP app.", "UPI_FAILURE"),
]

BANK_CODES = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK", "PUNB"]

CUSTOMER_VALUE_TIERS = ["low", "mid", "high"]


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def make_row(i: int) -> dict:
    method = weighted_choice([
        ("card", 0.38), ("upi", 0.40), ("netbanking", 0.12),
        ("wallet", 0.06), ("emi", 0.04),
    ])

    # UPI-history / card-history correlations (mirrors real repeat-customer
    # behaviour: someone who mostly pays by UPI has a high upi_success_rate).
    upi_success_rate = round(random.betavariate(6, 2) if method == "upi" else random.betavariate(3, 3), 3)
    card_success_rate = round(random.betavariate(6, 2) if method == "card" else random.betavariate(3, 3), 3)
    previous_success_rate = round((upi_success_rate + card_success_rate) / 2 + random.uniform(-0.05, 0.05), 3)
    previous_success_rate = min(max(previous_success_rate, 0.0), 1.0)
    previous_failure_rate = round(1 - previous_success_rate, 3)

    attempt_number = weighted_choice([(1, 0.55), (2, 0.30), (3, 0.12), (4, 0.03)])
    customer_value_tier = weighted_choice([("low", 0.4), ("mid", 0.4), ("high", 0.2)])
    amount_paise = {
        "low": random.randint(20000, 150000),
        "mid": random.randint(150000, 800000),
        "high": random.randint(800000, 5000000),
    }[customer_value_tier]

    err = random.choice(FAILURE_TEMPLATES)
    error_code, error_source, error_step, error_reason, error_desc, root_cause = err

    # Method-specific coherence: UPI failures should mostly carry upi-ish
    # reasons, card failures card-ish reasons, network timeouts any method.
    if root_cause == "UPI_FAILURE" and method != "upi":
        method = "upi"
    if root_cause == "CARD_FAILURE" and method not in ("card", "emi"):
        method = "card"

    hour = random.randint(0, 23)
    day_of_week = random.randint(0, 6)
    checkout_duration_sec = random.randint(15, 400)
    time_since_last_attempt_min = 0 if attempt_number == 1 else random.randint(1, 2880)

    # --- Ground-truth recovery outcome (label), used to train/evaluate ---
    # Recovery likelihood driven by root cause + account history, mirroring
    # the correlations Day-2 of the plan calls for (e.g. strong UPI history
    # + card failure -> alternate UPI recovers well).
    base = {
        "NETWORK_TIMEOUT": 0.72,
        "CARD_FAILURE": 0.55,
        "UPI_FAILURE": 0.50,
        "USER_ABANDONMENT": 0.35,
        "RETRY_LIMIT": 0.10,
        "BANK_DECLINE": 0.30,
    }[root_cause]
    score = base + 0.25 * previous_success_rate - 0.05 * (attempt_number - 1)
    score = min(max(score, 0.02), 0.97)
    recovered = 1 if random.random() < score else 0

    if attempt_number >= 3:
        recovery_action = "escalate"
    elif root_cause == "NETWORK_TIMEOUT":
        recovery_action = "retry"
    elif root_cause == "CARD_FAILURE" and upi_success_rate > 0.5:
        recovery_action = "switch_to_upi"
    elif root_cause == "USER_ABANDONMENT":
        recovery_action = "send_reminder"
    elif score < 0.15:
        recovery_action = "stop"
    else:
        recovery_action = "retry"

    now = int(time.time())
    return {
        # This row IS the original failed-payment event (revenue at risk).
        # `recovered` / `recovery_action` below are the outcome of the
        # recovery attempt the agent takes on it, not the original payment.
        "id": f"pay_{i:014d}",
        "order_id": f"order_{i:014d}",
        "entity": "payment",
        "amount": amount_paise,
        "currency": "INR",
        "status": "failed",
        "method": method,
        "captured": False,
        "email": f"customer{i}@example.com",
        "contact": f"+9198{random.randint(10000000, 99999999)}",
        "customer_id": f"cust_{i % 400:010d}",
        "bank": random.choice(BANK_CODES) if method in ("card", "netbanking") else "",
        "error_code": error_code,
        "error_description": error_desc,
        "error_source": error_source,
        "error_step": error_step,
        "error_reason": error_reason,
        "root_cause": root_cause,
        "created_at": now - random.randint(0, 30 * 86400),
        "attempt_number": attempt_number,
        "previous_success_rate": previous_success_rate,
        "previous_failure_rate": previous_failure_rate,
        "upi_success_rate": upi_success_rate,
        "card_success_rate": card_success_rate,
        "time_since_last_attempt_min": time_since_last_attempt_min,
        "hour": hour,
        "day_of_week": day_of_week,
        "checkout_duration_sec": checkout_duration_sec,
        "customer_value_tier": customer_value_tier,
        "recovered": recovered,
        "recovery_action": recovery_action,
    }


def main():
    rows = [make_row(i) for i in range(N_ROWS)]
    fieldnames = list(rows[0].keys())
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    n_failed = sum(1 for r in rows if r["status"] == "failed")
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")
    print(f"  failed/at-risk payments: {n_failed}")
    print(f"  captured payments:       {len(rows) - n_failed}")


if __name__ == "__main__":
    main()
