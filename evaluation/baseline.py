"""
Baseline policy: every failed payment gets retried exactly once, no
diagnosis, no ML, no policy engine. This is what the AI agent has to
beat, and beating it is the headline number of the whole project.

Run: python baseline.py
"""

import json
from pathlib import Path

import pandas as pd

import sys
sys.path.append(str(Path(__file__).parent.parent / "simulator"))
from simulate import execute_action

DATA_PATH = Path(__file__).parent.parent / "data" / "razorpay_demo_payments.csv"
OUT_PATH = Path(__file__).parent / "baseline_results.json"


def run_baseline(df: pd.DataFrame) -> dict:
    total_at_risk = int(df["amount"].sum())
    recovered_total = 0
    n_recovered = 0
    for _, row in df.iterrows():
        result = execute_action(row.to_dict(), "retry")
        recovered_total += result["recovered_amount"]
        if result["outcome"] == "SUCCESS":
            n_recovered += 1

    return {
        "policy": "baseline_retry_once",
        "n_transactions": len(df),
        "revenue_at_risk": total_at_risk,
        "revenue_recovered": recovered_total,
        "recovery_rate": round(n_recovered / len(df), 4),
        "unnecessary_interventions": len(df) - n_recovered,  # retried but failed anyway
    }


def main():
    df = pd.read_csv(DATA_PATH)
    results = run_baseline(df)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
