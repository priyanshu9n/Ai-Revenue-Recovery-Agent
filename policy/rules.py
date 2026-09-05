"""
Policy / guardrail engine. This is the layer that makes the agent's
decisions auditable and bounded - the LLM/agent proposes an action, this
engine is the sole authority on whether it's ALLOWED, and the agent
cannot bypass it.

This directly implements the "compliant escalation, stopping rules" bar.

NOTE on policy_config: the constants below are the DEFAULT config, used
for the fully-built and evaluated "payment failure" recovery loop. Other
revenue-leak types (see agent/leak_types.py -- checkout drop-off, failed
subscriptions, B2B receivables, mandate retries, promise-to-pay) reuse this
exact same engine with their OWN policy_config (different cooldowns, retry
caps, escalation thresholds appropriate to that leak type), passed in
explicitly. If policy_config is omitted, behavior is 100% unchanged from
before this parameter existed.
"""

from dataclasses import dataclass, field

MAX_RETRIES = 2
MAX_REMINDERS_PER_24H = 1
MAX_METHOD_SWITCHES = 1
LOW_PROBABILITY_STOP_THRESHOLD = 0.20
ESCALATE_AFTER_ATTEMPTS = 3
COOLDOWN_MINUTES = {
    "NETWORK_TIMEOUT": 10,
    "CARD_FAILURE": 30,
    "UPI_FAILURE": 15,
    "USER_ABANDONMENT": 60,
    "BANK_DECLINE": 120,
    "RETRY_LIMIT": 0,   # not eligible for retry regardless of cooldown
    "UNKNOWN": 60,
}

DEFAULT_POLICY_CONFIG = {
    "max_retries": MAX_RETRIES,
    "max_reminders_per_24h": MAX_REMINDERS_PER_24H,
    "max_method_switches": MAX_METHOD_SWITCHES,
    "low_probability_stop_threshold": LOW_PROBABILITY_STOP_THRESHOLD,
    "escalate_after_attempts": ESCALATE_AFTER_ATTEMPTS,
    "cooldown_minutes": COOLDOWN_MINUTES,
    "non_retryable_root_causes": {"RETRY_LIMIT"},
}

KNOWN_METHODS = {"card", "upi", "netbanking", "wallet", "emi"}
BASE_ACTIONS = {"retry", "send_reminder", "escalate", "stop", "wait"}
# Any switch_to_<method> for a known method is a valid action -- this is what
# lets the agent choose from ALL payment methods (via predict_recovery_by_method)
# instead of only ever switching between card and UPI.
ALLOWED_ACTIONS = BASE_ACTIONS | {f"switch_to_{m}" for m in KNOWN_METHODS}


def _is_method_switch(action: str) -> bool:
    return action in {f"switch_to_{m}" for m in KNOWN_METHODS}


@dataclass
class PolicyDecision:
    allowed: bool
    action: str
    reason: str
    violations: list = field(default_factory=list)


def evaluate_policy(transaction: dict, proposed_action: str, recovery_probability: float,
                     customer_opted_out: bool = False, policy_config: dict = None,
                     extra_allowed_actions: set = None) -> PolicyDecision:
    """
    transaction: dict with at least attempt_number, root_cause,
                 time_since_last_attempt_min, and (for reminders/switches)
                 counts of prior actions this cycle if tracked upstream.
    proposed_action: what the agent wants to do.
    recovery_probability: P(recovery) from the ML model.
    policy_config: override thresholds (see DEFAULT_POLICY_CONFIG). Leave
                   None for the payment-failure loop's exact original behavior.
    extra_allowed_actions: action vocabulary beyond the payment-failure set
                   (e.g. "send_gentle_reminder", "cancel_subscription") for
                   other leak types.
    """
    cfg = policy_config or DEFAULT_POLICY_CONFIG
    allowed_actions = ALLOWED_ACTIONS | (extra_allowed_actions or set())
    violations = []
    attempts = int(transaction.get("attempt_number", 1))
    root_cause = transaction.get("root_cause", "UNKNOWN")
    cooldown_elapsed = int(transaction.get("time_since_last_attempt_min", 0))

    if proposed_action not in allowed_actions:
        return PolicyDecision(False, "stop", f"Unrecognized action '{proposed_action}'.", ["unknown_action"])

    # Hard stop: opted out
    if customer_opted_out:
        return PolicyDecision(False, "stop", "Customer has opted out of recovery contact.", ["customer_opt_out"])

    escalate_after = cfg["escalate_after_attempts"]
    # Hard stop: attempt ceiling reached -> only escalate or stop allowed
    if attempts >= escalate_after and proposed_action not in ("escalate", "stop"):
        violations.append("attempt_ceiling_exceeded")
        return PolicyDecision(False, "escalate",
                               f"Attempt {attempts} >= escalation threshold ({escalate_after}); "
                               f"escalating instead of {proposed_action}.", violations)

    prob_floor = cfg["low_probability_stop_threshold"]
    # Hard stop: probability floor
    if recovery_probability < prob_floor and proposed_action not in ("stop", "escalate"):
        violations.append("below_probability_floor")
        return PolicyDecision(False, "stop",
                               f"P(recovery)={recovery_probability:.2f} below floor "
                               f"({prob_floor}); stopping.", violations)

    # Retry-specific rules
    if proposed_action == "retry":
        if root_cause in cfg["non_retryable_root_causes"]:
            return PolicyDecision(False, "stop", "Root cause flagged as non-retryable (risk/business decline).",
                                   ["non_retryable_root_cause"])
        max_retries = cfg["max_retries"]
        if attempts > max_retries:
            return PolicyDecision(False, "escalate", f"Retry attempts ({attempts}) exceed max ({max_retries}).",
                                   ["retry_limit_exceeded"])
        required_cooldown = cfg["cooldown_minutes"].get(root_cause, 60)
        if cooldown_elapsed < required_cooldown and attempts > 1:
            return PolicyDecision(False, "wait",
                                   f"Cooldown not met: {cooldown_elapsed}min elapsed, "
                                   f"{required_cooldown}min required for {root_cause}.",
                                   ["cooldown_not_met"])

    # Reminder-specific rules (covers send_reminder and leak-type reminder variants)
    if proposed_action == "send_reminder" or proposed_action.endswith("_reminder"):
        reminders_sent_24h = int(transaction.get("reminders_sent_24h", 0))
        if reminders_sent_24h >= cfg["max_reminders_per_24h"]:
            return PolicyDecision(False, "stop", "Reminder cap reached for 24h window.",
                                   ["reminder_cap_exceeded"])

    # Method-switch rules (any switch_to_<method>, not just UPI/card)
    if _is_method_switch(proposed_action):
        switches_used = int(transaction.get("method_switches_used", 0))
        if switches_used >= cfg["max_method_switches"]:
            return PolicyDecision(False, "send_reminder",
                                   "Method-switch cap reached; falling back to reminder.",
                                   ["method_switch_cap_exceeded"])

    return PolicyDecision(True, proposed_action, "Action permitted under current policy.", [])


if __name__ == "__main__":
    txn = {"attempt_number": 1, "root_cause": "NETWORK_TIMEOUT", "time_since_last_attempt_min": 0}
    print(evaluate_policy(txn, "retry", recovery_probability=0.7))

