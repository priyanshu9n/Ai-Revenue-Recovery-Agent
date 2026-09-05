"""
run_recovery_evaluation() - the single command that produces the
headline numbers for the pitch: revenue at risk, baseline recovered,
AI recovered, uplift, policy violations, audit coverage.

Run: python run_evaluation.py
Outputs: evaluation_results.json, audit_log.csv
"""

import json
from pathlib import Path

import pandas as pd

import sys
sys.path.append(str(Path(__file__).parent.parent / "agent"))
sys.path.append(str(Path(__file__).parent.parent / "common"))
sys.path.append(str(Path(__file__).parent))
from agent import run_recovery_cycle
from baseline import run_baseline
from currency import format_inr

DATA_PATH = Path(__file__).parent.parent / "data" / "razorpay_demo_payments.csv"
RESULTS_PATH = Path(__file__).parent / "evaluation_results.json"
AUDIT_LOG_PATH = Path(__file__).parent / "audit_log.csv"


def run_recovery_evaluation(sample_size: int = None, use_llm: bool = False) -> dict:
    df = pd.read_csv(DATA_PATH)
    if sample_size:
        df = df.sample(n=min(sample_size, len(df)), random_state=7).reset_index(drop=True)

    baseline = run_baseline(df)

    records = []
    for _, row in df.iterrows():
        record = run_recovery_cycle(row.to_dict(), use_llm=use_llm)
        records.append(record)

    revenue_at_risk = int(df["amount"].sum())
    ai_recovered = sum(r["recovered_amount"] for r in records)
    ai_recovery_rate = sum(1 for r in records if r["outcome"] == "SUCCESS") / len(records)

    policy_violations = sum(1 for r in records if r["policy_violations"])
    # Real safety check: a violation was flagged BUT the disallowed action
    # executed anyway (i.e. the policy engine failed to override it). This
    # should always be 0 -- the guardrail's whole job is to prevent this.
    exceeded_retry_limits = sum(
        1 for r in records
        if r["policy_violations"] and r["policy_allowed"]
    )
    audit_coverage = sum(1 for r in records if r["trace"]) / len(records)

    uplift_pct = None
    if baseline["revenue_recovered"] > 0:
        uplift_pct = round(
            (ai_recovered - baseline["revenue_recovered"]) / baseline["revenue_recovered"] * 100, 2
        )

    summary = {
        "n_transactions": len(records),
        "revenue_at_risk_paise": revenue_at_risk,
        "baseline_recovered_paise": baseline["revenue_recovered"],
        "ai_recovered_paise": ai_recovered,
        "additional_revenue_recovered_paise": ai_recovered - baseline["revenue_recovered"],
        "recovery_uplift_pct": uplift_pct,
        "baseline_recovery_rate": baseline["recovery_rate"],
        "ai_recovery_rate": round(ai_recovery_rate, 4),
        "policy_violations_surfaced_and_blocked": policy_violations,
        "exceeded_retry_limits_that_executed_anyway": exceeded_retry_limits,  # should always be 0
        "audit_coverage": round(audit_coverage, 4),
        "action_distribution": pd.Series([r["final_action"] for r in records]).value_counts().to_dict(),
    }

    # Save audit log (flat, without the nested trace, for easy inspection / dashboard use)
    audit_df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "trace"} for r in records
    ])
    audit_df.to_csv(AUDIT_LOG_PATH, index=False)

    with open(RESULTS_PATH, "w") as f:
        json.dump({"summary": summary, "baseline": baseline}, f, indent=2)

    return {"summary": summary, "baseline": baseline, "records": records}


def print_report(summary: dict):
    rupees = format_inr

    print("─" * 55)
    print("AI REVENUE RECOVERY EVALUATION")
    print("─" * 55)
    print(f"Evaluation transactions      {summary['n_transactions']:,}")
    print()
    print(f"Revenue at risk              {rupees(summary['revenue_at_risk_paise'])}")
    print()
    print(f"Baseline recovered           {rupees(summary['baseline_recovered_paise'])}")
    print(f"AI recovered                 {rupees(summary['ai_recovered_paise'])}")
    print(f"Additional revenue recovered {rupees(summary['additional_revenue_recovered_paise'])}")
    print()
    print(f"Recovery uplift              {summary['recovery_uplift_pct']}%")
    print()
    print(f"Policy violations blocked    {summary['policy_violations_surfaced_and_blocked']}")
    print(f"Exceeded retry limits (bug)  {summary['exceeded_retry_limits_that_executed_anyway']}")
    print(f"Audit coverage               {summary['audit_coverage']*100:.1f}%")
    print("─" * 55)


if __name__ == "__main__":
    result = run_recovery_evaluation()
    print_report(result["summary"])
    print(f"\nFull results -> {RESULTS_PATH}")
    print(f"Audit log     -> {AUDIT_LOG_PATH}")
