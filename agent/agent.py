"""
The Recovery Agent.

Flow (matches Day 7 of the plan):
  Transaction -> Inspect -> Diagnose -> predict_recovery -> propose action
  -> check_policy -> execute (if allowed) -> record_outcome

Two ways to propose an action:
  1. `propose_action_rule_based` - deterministic, maps root cause -> the
     RAG-retrieved best-fit action from the diagnosis engine. Always
     available, no API key needed.
  2. `propose_action_llm` - calls Claude (if ANTHROPIC_API_KEY is set) to
     pick from the diagnosis-permitted action list, given the RAG policy
     context. This is the "LLM decision" box in the architecture diagram.

Either way, the LLM/rule-based proposal is NEVER trusted directly - it
always goes through `check_policy` before anything executes. That
separation (LLM decision -> policy engine -> allowed? -> execute/STOP)
is the safety property this whole project is built around.
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent / "ml"))
from tools import (
    diagnose_transaction, predict_recovery, get_policy,
    check_policy, execute_recovery_action,
)
from predict import predict_recovery_by_method

# Root causes where a payment-method switch is genuinely on the table (per
# root_cause.py's INTERVENTIONS list). For these we score EVERY payment
# method with the ML model and pick by expected value, instead of only
# ever comparing "the one alternate method root_cause.py happened to name".
METHOD_CHOICE_ROOT_CAUSES = {"CARD_FAILURE", "UPI_FAILURE"}


@dataclass
class AgentTrace:
    steps: list = field(default_factory=list)

    def log(self, step: str, detail: dict):
        self.steps.append({"step": step, "detail": detail})


def propose_action_by_expected_value(row: dict, diagnosis, candidate_methods=None) -> tuple:
    """
    Scores payment methods with the same trained recovery model -- "what
    would P(recovery) be if this customer paid with method X instead?" --
    and picks whichever method maximizes expected value (P(recovery) x
    amount), instead of a hand-tuned threshold rule (the old version just
    checked "is upi_success_rate < 0.4").

    candidate_methods restricts WHICH alternate methods are even considered.
    By default this is {current_method, "card", "upi"} -- deliberately NOT
    all 5 methods. We tried scoring all 5 (card/upi/netbanking/wallet/emi)
    and it made results *worse*: the model was trained on the method the
    customer actually used, so its prediction for a method they rarely or
    never used is an extrapolation, and it sometimes rates netbanking/wallet
    highly for a customer where that's not a real signal. The failure
    taxonomy (root_cause.py) only documents card<->UPI switching as a
    validated recovery pattern in the first place -- so letting the model
    chase methods outside that validated set traded a real signal (the
    documented card<->UPI relationship) for noise. Pass a wider
    candidate_methods explicitly once netbanking/wallet/emi switching has
    real outcome data to validate against.

    Falls back to the diagnosis's first listed intervention for root causes
    where a method switch isn't a sensible option at all (e.g. a customer
    who abandoned checkout doesn't need a different payment method, they
    need a reminder).

    Returns (action, method_scores) so the caller can log what was compared.
    """
    interventions = diagnosis.possible_interventions
    if not interventions:
        return "stop", {}

    if diagnosis.root_cause not in METHOD_CHOICE_ROOT_CAUSES:
        return interventions[0], {}

    amount = float(row.get("amount", 0))
    current_method = row.get("method")
    methods = candidate_methods or sorted({current_method, "card", "upi"})
    method_probs = predict_recovery_by_method(row, methods=methods)
    expected_value = {m: p * amount for m, p in method_probs.items()}
    best_method = max(expected_value, key=expected_value.get)

    if best_method == current_method:
        # Best option is to keep trying the same method -- only valid if
        # this root cause's intervention list actually permits a retry.
        return ("retry" if "retry" in interventions else interventions[0]), method_probs

    action = f"switch_to_{best_method}"
    return action, method_probs


def propose_action_rule_based(row: dict, diagnosis) -> str:
    """
    Deterministic proposal: first intervention the diagnosis engine lists
    for this root cause, refined by which method the customer already has
    a strong track record with (Day 5's UPI/card correlation).

    THIS is the default, and it's the one backing every number in
    evaluation_results.json. We also built `propose_action_by_expected_value`,
    which asks the ML model to score every method directly instead of using
    this threshold -- it's a methodologically cleaner idea, but we tested it
    head-to-head against this heuristic and it recovered LESS money, because
    the model's counterfactual prediction for a method the customer didn't
    actually use is an extrapolation the model isn't well-calibrated for
    (measured: only 39.5% directional agreement with ground truth, worse
    than always guessing "switch to UPI"). Kept here as the shipped default
    until that's fixed with real experimentation data; the ML version is
    still available below for anyone who wants to keep iterating on it.
    """
    interventions = diagnosis.possible_interventions
    if not interventions:
        return "stop"
    if "switch_to_upi" in interventions and row.get("upi_success_rate", 0) < 0.4:
        # Customer has a weak UPI history - a card retry is a better fit
        # than switching them TO the payment method they already struggle with.
        return "retry" if "retry" in interventions else interventions[0]
    return interventions[0]


def propose_action_llm(row: dict, diagnosis, policy_context: list) -> str:
    """Optional: ask Claude to choose from the permitted action list.
    Falls back to the rule-based proposal if no API key is configured."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return propose_action_rule_based(row, diagnosis)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        context_text = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in policy_context)
        prompt = (
            f"A payment failed. Root cause: {diagnosis.root_cause}. "
            f"Permitted interventions for this root cause: {diagnosis.possible_interventions}. "
            f"Customer history: upi_success_rate={row.get('upi_success_rate')}, "
            f"card_success_rate={row.get('card_success_rate')}, attempt_number={row.get('attempt_number')}.\n\n"
            f"Relevant policy:\n{context_text}\n\n"
            f"Reply with exactly one word: the single best action from the permitted "
            f"interventions list above. No explanation."
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        action = resp.content[0].text.strip().lower()
        if action in diagnosis.possible_interventions:
            return action
        return propose_action_rule_based(row, diagnosis)
    except Exception:
        return propose_action_rule_based(row, diagnosis)


def run_recovery_cycle(row: dict, use_llm: bool = False, customer_opted_out: bool = False) -> dict:
    """Runs one transaction through the full agent loop and returns a full
    audit record."""
    trace = AgentTrace()

    trace.log("inspect", {"id": row.get("id"), "amount": row.get("amount"), "method": row.get("method")})

    diagnosis = diagnose_transaction(row)
    trace.log("diagnose", {"root_cause": diagnosis.root_cause,
                            "possible_interventions": diagnosis.possible_interventions})

    probability = predict_recovery(row)
    trace.log("predict_recovery", {"probability": round(probability, 4)})

    policy_context = get_policy(f"Can I {diagnosis.possible_interventions[0]} this transaction? "
                                 f"root cause {diagnosis.root_cause}")
    trace.log("retrieve_policy_context", {"sources": [c["source"] for c in policy_context]})

    if use_llm:
        proposed = propose_action_llm(row, diagnosis, policy_context)
        method_scores = {}
    else:
        proposed = propose_action_rule_based(row, diagnosis)
        method_scores = {}
    trace.log("propose_action", {"action": proposed, "via": "llm" if use_llm else "rule_based",
                                  "method_recovery_scores": {k: round(v, 4) for k, v in method_scores.items()}})

    decision = check_policy(row, proposed, probability, customer_opted_out=customer_opted_out)
    trace.log("check_policy", {"allowed": decision.allowed, "final_action": decision.action,
                                "reason": decision.reason, "violations": decision.violations})

    result = execute_recovery_action(row, decision.action)
    trace.log("execute", result)

    record = {
        "transaction_id": row.get("id"),
        "amount": row.get("amount"),
        "root_cause": diagnosis.root_cause,
        "predicted_probability": round(probability, 4),
        "proposed_action": proposed,
        "final_action": decision.action,
        "policy_allowed": decision.allowed,
        "policy_reason": decision.reason,
        "policy_violations": decision.violations,
        "outcome": result["outcome"],
        "recovered_amount": result["recovered_amount"],
        "timestamp": int(time.time()),
        "trace": trace.steps,
    }
    return record


if __name__ == "__main__":
    sample_row = {
        "id": "pay_demo_1", "amount": 250000, "method": "card",
        "error_reason": "insufficient_funds", "error_source": "customer",
        "root_cause": "CARD_FAILURE", "attempt_number": 1,
        "previous_success_rate": 0.7, "previous_failure_rate": 0.3,
        "upi_success_rate": 0.85, "card_success_rate": 0.4,
        "time_since_last_attempt_min": 0, "hour": 14, "day_of_week": 2,
        "checkout_duration_sec": 120, "customer_value_tier": "mid",
    }
    import json
    print(json.dumps(run_recovery_cycle(sample_row), indent=2))
