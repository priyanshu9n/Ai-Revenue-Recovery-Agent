# Product Specification — AI Revenue Recovery Agent

## Problem
Failed payments cause revenue leakage that is often recoverable — a retry
after a transient gateway timeout, or offering UPI to a customer whose card
failed, frequently succeeds. Merchants without a systematic recovery process
leave this money on the table or over-contact customers with blanket retries
that annoy without recovering much.

## User
Merchant payments / revenue operations teams using Razorpay.

## Agent objective
Maximize ₹ recovered from failed payments, subject to compliant intervention
limits and stopping rules (never spam a customer, never retry indefinitely,
always respect opt-outs).

## Failure categories (root causes)
| Root cause | Meaning | Typical Razorpay `error_reason` |
|---|---|---|
| NETWORK_TIMEOUT | Transient gateway/bank infra issue | `gateway_timeout`, `bank_server_error`, `internal_error` |
| CARD_FAILURE | Card declined/expired/insufficient funds | `insufficient_funds`, `card_expired` |
| UPI_FAILURE | UPI-specific decline | `upi_declined` |
| USER_ABANDONMENT | Customer dropped off mid-checkout | `incorrect_otp`, `otp_timeout` |
| BANK_DECLINE | Bank actively declined | `payment_declined` |
| RETRY_LIMIT | Risk/business rule decline — not retryable | `risk_check_failed` |

## Recovery actions
`retry`, `switch_to_upi`, `switch_to_card`, `send_reminder`, `escalate`, `stop`

## Intervention limits & stopping rules (enforced by `policy/rules.py`)
- Max 2 retries per transaction; 3rd attempt forces escalation.
- Root-cause-specific cooldown before a retry is allowed (10–120 min).
- Max 1 reminder per 24h; max 1 payment-method switch per transaction.
- Hard stop if `recovery_probability < 0.20`.
- Hard stop if the customer has opted out of recovery contact.
- `RETRY_LIMIT` root cause is never retried regardless of probability.

## Success criteria / metrics
- **₹ recovered** (hero metric) and **recovery uplift** vs. a naive
  "retry every failure once" baseline.
- Recovery rate, policy violations caught, disallowed actions that executed
  anyway (must be 0), audit coverage (must be 100%).
- Model quality: ROC-AUC, PR-AUC, precision/recall, and a calibration check
  (actual recovery rate should rise monotonically with predicted-probability
  bucket).

## Out of scope for this build
Real production Razorpay integration (live path exists as an opt-in code
path, not the default), WhatsApp/SMS/voice infrastructure, multi-merchant
support, reinforcement learning, LLM fine-tuning, container orchestration.
