"""
Simulated execution environment. Tools like retry_payment() don't call
Razorpay's production API - they call into this simulator, which models
P(success | action, transaction) and returns SUCCESS/FAILURE plus the
recovered amount. This is what makes the closed loop measurable without
touching a real payment gateway.

The success-probability model here deliberately mirrors (but is
independent of) the labels in the demo dataset: same root-cause/action
correlations, so an agent that picks sensible actions should recover
more revenue than one that doesn't - which is exactly what Day 10's
evaluation is checking for.
"""

import hashlib
import random

# P(success) uplift/penalty by (root_cause, action) - independent random
# stream from the dataset labels, seeded per-call by transaction id so
# results are reproducible across repeated evaluation runs.
ACTION_FIT = {
    ("NETWORK_TIMEOUT", "retry"): 0.75,
    ("CARD_FAILURE", "switch_to_upi"): 0.65,
    ("CARD_FAILURE", "switch_to_netbanking"): 0.30,
    ("CARD_FAILURE", "switch_to_wallet"): 0.30,
    ("CARD_FAILURE", "switch_to_emi"): 0.20,
    ("CARD_FAILURE", "retry"): 0.35,
    ("UPI_FAILURE", "switch_to_card"): 0.55,
    ("UPI_FAILURE", "switch_to_netbanking"): 0.25,
    ("UPI_FAILURE", "switch_to_wallet"): 0.25,
    ("UPI_FAILURE", "switch_to_emi"): 0.15,
    ("UPI_FAILURE", "send_reminder"): 0.40,
    ("USER_ABANDONMENT", "send_reminder"): 0.45,
    ("BANK_DECLINE", "send_reminder"): 0.30,
    ("RETRY_LIMIT", "escalate"): 0.15,
}
DEFAULT_FIT = 0.10  # mismatched action / root cause: mostly fails
NO_OP_FIT = 0.0     # stop / wait: no recovery happens (by design)


def _seed_for(transaction_id: str, action: str) -> int:
    # NOTE: Python's built-in hash() is randomized per-process (PYTHONHASHSEED)
    # for strings, which would make every evaluation run produce different
    # numbers -- a reproducibility bug for exactly the kind of headline
    # metrics ("Evaluation reproducible" in the submission checklist) this
    # project needs to be trustworthy. hashlib.md5 is stable across runs
    # and processes.
    key = f"{transaction_id}|{action}".encode("utf-8")
    return int(hashlib.md5(key).hexdigest(), 16) % (2**32)


def execute_action(transaction: dict, action: str) -> dict:
    """
    Returns:
      {outcome: "SUCCESS"|"FAILURE"|"NO_ACTION", recovered_amount: int,
       probability_used: float}
    """
    txn_id = transaction.get("id", "unknown")
    root_cause = transaction.get("root_cause", "UNKNOWN")
    amount = int(transaction.get("amount", 0))

    if action in ("stop", "wait"):
        return {"outcome": "NO_ACTION", "recovered_amount": 0, "probability_used": NO_OP_FIT}

    fit = ACTION_FIT.get((root_cause, action), DEFAULT_FIT)

    rng = random.Random(_seed_for(txn_id, action))
    success = rng.random() < fit
    return {
        "outcome": "SUCCESS" if success else "FAILURE",
        "recovered_amount": amount if success else 0,
        "probability_used": fit,
    }


if __name__ == "__main__":
    txn = {"id": "pay_test", "root_cause": "NETWORK_TIMEOUT", "amount": 50000}
    print(execute_action(txn, "retry"))
