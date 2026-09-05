# Cooldown Rules

Cooldown periods exist to avoid hammering a bank/gateway that just
declined a transaction, and to avoid appearing as a duplicate-charge
attempt to the customer. Cooldown is measured from the time of the last
attempt on that transaction. A retry proposed before the cooldown window
has elapsed must be rejected by the policy engine with a WAIT decision,
not silently delayed - the decision must be visible in the audit trail.
