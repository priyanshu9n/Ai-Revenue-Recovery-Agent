"""
Run: pytest tests/

Smoke tests for the parts of the pipeline that are easy to silently break:
policy guardrails, root-cause mapping, simulator determinism, and the full
agent loop's safety property (an agent-proposed action never executes
unless the policy engine allowed it).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
for sub in ["agent", "policy", "simulator", "ml", "rag", "evaluation"]:
    sys.path.append(str(ROOT / sub))

from rules import evaluate_policy  # noqa: E402
from root_cause import diagnose, classify_root_cause  # noqa: E402
from simulate import execute_action  # noqa: E402
from agent import run_recovery_cycle  # noqa: E402


def test_root_cause_mapping_known_reason():
    assert classify_root_cause("gateway_timeout", "gateway", "card") == "NETWORK_TIMEOUT"
    assert classify_root_cause("insufficient_funds", "customer", "card") == "CARD_FAILURE"


def test_root_cause_mapping_unknown_falls_back():
    assert classify_root_cause("totally_unrecognized_code", "", "") == "UNKNOWN"


def test_diagnosis_lists_interventions():
    d = diagnose({"error_reason": "upi_declined", "error_source": "bank", "method": "upi"})
    assert d.root_cause == "UPI_FAILURE"
    assert "switch_to_card" in d.possible_interventions


def test_simulator_is_deterministic_across_calls():
    txn = {"id": "pay_repro_test", "root_cause": "NETWORK_TIMEOUT", "amount": 10000}
    r1 = execute_action(txn, "retry")
    r2 = execute_action(txn, "retry")
    assert r1 == r2


def test_policy_blocks_low_probability():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "BANK_DECLINE",
                          "time_since_last_attempt_min": 200}, "retry", 0.05)
    assert d.allowed is False


def test_agent_never_executes_a_blocked_action():
    """Safety property: if the policy engine says not allowed, the action
    that actually gets executed must be the policy's substitute (stop /
    wait / escalate / send_reminder), never the raw proposed action."""
    row = {
        "id": "pay_blocked_test", "amount": 50000, "method": "card",
        "error_reason": "risk_check_failed", "error_source": "business",
        "attempt_number": 1, "root_cause": "RETRY_LIMIT",
        "upi_success_rate": 0.9, "card_success_rate": 0.2,
        "time_since_last_attempt_min": 0, "hour": 12, "day_of_week": 2,
        "previous_success_rate": 0.5, "previous_failure_rate": 0.5,
        "checkout_duration_sec": 60, "customer_value_tier": "mid",
    }
    record = run_recovery_cycle(row)
    if not record["policy_allowed"]:
        assert record["final_action"] != record["proposed_action"] or record["final_action"] in (
            "stop", "wait", "escalate", "send_reminder")


def test_opted_out_customer_always_stops():
    row = {
        "id": "pay_optout_test", "amount": 50000, "method": "card",
        "error_reason": "gateway_timeout", "error_source": "gateway",
        "attempt_number": 1, "root_cause": "NETWORK_TIMEOUT",
        "upi_success_rate": 0.9, "card_success_rate": 0.8,
        "time_since_last_attempt_min": 0, "hour": 12, "day_of_week": 2,
        "previous_success_rate": 0.8, "previous_failure_rate": 0.2,
        "checkout_duration_sec": 60, "customer_value_tier": "high",
    }
    record = run_recovery_cycle(row, customer_opted_out=True)
    assert record["final_action"] == "stop"
    assert record["recovered_amount"] == 0
