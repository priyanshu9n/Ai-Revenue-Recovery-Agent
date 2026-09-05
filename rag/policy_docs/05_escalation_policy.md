# Escalation Policy

A transaction is escalated to a human operator once it reaches 3 recovery
attempts, regardless of the model's predicted recovery probability at
that point. Escalation is also the fallback action whenever the agent's
proposed action would otherwise be blocked and no safe automatic
fallback exists (e.g. retries exhausted).
