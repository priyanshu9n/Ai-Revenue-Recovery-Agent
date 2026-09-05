"""Run: python policy_tests.py  (or `pytest policy_tests.py`)"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from rules import evaluate_policy


def test_opt_out_hard_stops():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "NETWORK_TIMEOUT",
                          "time_since_last_attempt_min": 100}, "retry", 0.8, customer_opted_out=True)
    assert d.allowed is False and d.action == "stop"


def test_low_probability_stops():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "BANK_DECLINE",
                          "time_since_last_attempt_min": 200}, "retry", 0.05)
    assert d.allowed is False and d.action == "stop"


def test_attempt_ceiling_forces_escalation():
    d = evaluate_policy({"attempt_number": 3, "root_cause": "NETWORK_TIMEOUT",
                          "time_since_last_attempt_min": 200}, "retry", 0.8)
    assert d.allowed is False and d.action == "escalate"


def test_retry_limit_root_cause_blocks_retry():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "RETRY_LIMIT",
                          "time_since_last_attempt_min": 200}, "retry", 0.5)
    assert d.allowed is False and d.action == "stop"


def test_cooldown_blocks_early_retry():
    d = evaluate_policy({"attempt_number": 2, "root_cause": "BANK_DECLINE",
                          "time_since_last_attempt_min": 5}, "retry", 0.5)
    assert d.allowed is False and d.action == "wait"


def test_reminder_cap():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "USER_ABANDONMENT",
                          "time_since_last_attempt_min": 200, "reminders_sent_24h": 1}, "send_reminder", 0.4)
    assert d.allowed is False and d.action == "stop"


def test_method_switch_cap_falls_back_to_reminder():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "CARD_FAILURE",
                          "time_since_last_attempt_min": 200, "method_switches_used": 1}, "switch_to_upi", 0.6)
    assert d.allowed is False and d.action == "send_reminder"


def test_valid_retry_is_allowed():
    d = evaluate_policy({"attempt_number": 1, "root_cause": "NETWORK_TIMEOUT",
                          "time_since_last_attempt_min": 0}, "retry", 0.7)
    assert d.allowed is True and d.action == "retry"


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL  {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")


if __name__ == "__main__":
    run_all()
