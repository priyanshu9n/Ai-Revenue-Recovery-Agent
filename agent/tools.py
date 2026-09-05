"""
Tools the recovery agent can call. Each tool is a thin, auditable
wrapper - the agent never touches the simulator, policy engine, or ML
model directly except through these functions, so every action shows up
in one place for the audit log.
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent / "ml"))
sys.path.append(str(Path(__file__).parent.parent / "policy"))
sys.path.append(str(Path(__file__).parent.parent / "simulator"))
sys.path.append(str(Path(__file__).parent.parent / "rag"))

from root_cause import diagnose
from predict import predict_recovery_probability
from rules import evaluate_policy
from simulate import execute_action
from retriever import retrieve


def get_transaction(row: dict) -> dict:
    """Tool: return the raw transaction record (already have it from the CSV/API)."""
    return row


def get_customer_history(row: dict) -> dict:
    """Tool: surface the customer-history features already attached to the row."""
    return {
        "previous_success_rate": row.get("previous_success_rate"),
        "upi_success_rate": row.get("upi_success_rate"),
        "card_success_rate": row.get("card_success_rate"),
        "attempt_number": row.get("attempt_number"),
    }


def diagnose_transaction(row: dict):
    """Tool: deterministic root-cause diagnosis."""
    return diagnose(row)


def predict_recovery(row: dict) -> float:
    """Tool: ML model P(recovery)."""
    return predict_recovery_probability(row)


def get_policy(query: str):
    """Tool: RAG retrieval over policy documents."""
    return retrieve(query)


def check_policy(row: dict, proposed_action: str, probability: float, customer_opted_out: bool = False):
    """Tool: the ONE authority on whether an action may execute."""
    return evaluate_policy(row, proposed_action, probability, customer_opted_out)


def execute_recovery_action(row: dict, action: str):
    """Tool: run the action through the simulated payment environment."""
    return execute_action(row, action)
