"""
Deterministic root-cause diagnosis for a failed Razorpay payment.

Deliberately NOT an LLM call - this is a rules-based lookup over
Razorpay's own documented error taxonomy (error_reason / error_source /
error_step from https://razorpay.com/docs/api/errors/), because failure
classification here is a closed, well-documented mapping and doesn't
need probabilistic reasoning.

Buckets (matching the buildathon plan, Day 5):
    NETWORK_TIMEOUT   - transient infra/gateway/bank issue
    CARD_FAILURE      - card declined / expired / insufficient funds
    UPI_FAILURE       - UPI-specific decline
    USER_ABANDONMENT  - customer dropped off (OTP timeout, no action)
    BANK_DECLINE      - bank actively declined the transaction
    RETRY_LIMIT       - risk/business rule declines; don't keep retrying
    UNKNOWN           - anything not covered above
"""

from dataclasses import dataclass

# reason -> root cause, keyed on Razorpay's documented error_reason values
REASON_MAP = {
    "bank_server_error": "NETWORK_TIMEOUT",
    "gateway_timeout": "NETWORK_TIMEOUT",
    "internal_error": "NETWORK_TIMEOUT",
    "insufficient_funds": "CARD_FAILURE",
    "card_expired": "CARD_FAILURE",
    "upi_declined": "UPI_FAILURE",
    "incorrect_otp": "USER_ABANDONMENT",
    "otp_timeout": "USER_ABANDONMENT",
    "payment_declined": "BANK_DECLINE",
    "risk_check_failed": "RETRY_LIMIT",
}

# Fallback by (error_source, method) when reason isn't in the map above
SOURCE_METHOD_FALLBACK = {
    ("bank", "card"): "CARD_FAILURE",
    ("bank", "upi"): "UPI_FAILURE",
    ("gateway", None): "NETWORK_TIMEOUT",
    ("customer", None): "USER_ABANDONMENT",
    ("business", None): "RETRY_LIMIT",
}

INTERVENTIONS = {
    "NETWORK_TIMEOUT": ["retry"],
    "CARD_FAILURE": ["switch_to_upi", "retry"],
    "UPI_FAILURE": ["switch_to_card", "send_reminder"],
    "USER_ABANDONMENT": ["send_reminder"],
    "BANK_DECLINE": ["send_reminder", "stop"],
    "RETRY_LIMIT": ["stop", "escalate"],
    "UNKNOWN": ["stop"],
}


def classify_root_cause(error_reason: str, error_source: str, method: str) -> str:
    error_reason = (error_reason or "").strip()
    error_source = (error_source or "").strip()
    method = (method or "").strip()

    if error_reason in REASON_MAP:
        return REASON_MAP[error_reason]

    if (error_source, method) in SOURCE_METHOD_FALLBACK:
        return SOURCE_METHOD_FALLBACK[(error_source, method)]
    if (error_source, None) in SOURCE_METHOD_FALLBACK:
        return SOURCE_METHOD_FALLBACK[(error_source, None)]

    return "UNKNOWN"


@dataclass
class Diagnosis:
    root_cause: str
    possible_interventions: list


def diagnose(transaction: dict) -> Diagnosis:
    """
    transaction: dict with at least error_reason, error_source, method
    (either straight from the CSV row or a live Razorpay payment entity).
    """
    root_cause = transaction.get("root_cause") or classify_root_cause(
        transaction.get("error_reason", ""),
        transaction.get("error_source", ""),
        transaction.get("method", ""),
    )
    return Diagnosis(
        root_cause=root_cause,
        possible_interventions=INTERVENTIONS.get(root_cause, ["stop"]),
    )


if __name__ == "__main__":
    sample = {
        "error_reason": "upi_declined",
        "error_source": "bank",
        "method": "upi",
    }
    d = diagnose(sample)
    print(d)
