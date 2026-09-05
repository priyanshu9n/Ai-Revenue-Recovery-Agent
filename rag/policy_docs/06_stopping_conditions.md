# Stopping Conditions

Recovery must stop immediately (no further attempts of any kind) when:
1. The customer has explicitly opted out of contact.
2. The predicted recovery probability falls below 0.20.
3. The root cause is RETRY_LIMIT (a risk/business decline) and no
   escalation has been requested.
A stop decision must always be logged with the reason and probability
that triggered it, for audit purposes.
