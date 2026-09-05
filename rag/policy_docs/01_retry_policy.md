# Retry Policy

Failed payments may be retried only if the root cause is retryable:
NETWORK_TIMEOUT, CARD_FAILURE, and UPI_FAILURE are retryable. RETRY_LIMIT
(risk/business decline) is never retryable.

A maximum of 2 retries is allowed per transaction. On the 3rd attempt, the
transaction must be escalated instead of retried, regardless of predicted
recovery probability.

Retries must respect a cooldown period before being attempted again:
NETWORK_TIMEOUT (10 min), UPI_FAILURE (15 min), CARD_FAILURE (30 min),
BANK_DECLINE (120 min). Retrying before the cooldown elapses is a policy
violation.
