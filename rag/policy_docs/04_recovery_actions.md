# Recovery Actions

Permitted recovery actions are: retry, switch_to_upi, switch_to_card,
send_reminder, escalate, stop. No other action may be executed by the
agent. switch_to_upi/switch_to_card are capped at 1 use per transaction;
if the cap is already used, the policy engine downgrades the action to
send_reminder rather than blocking recovery entirely.
