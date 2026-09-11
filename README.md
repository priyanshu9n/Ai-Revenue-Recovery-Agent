# AI Revenue Recovery Agent
https://priyanshu9n-ai-revenue-recovery-agent.streamlit.app/

**Detects payment revenue at risk → diagnoses the failure → estimates
recovery probability → chooses a compliant recovery action → executes it
through tools → measures ₹ recovered → maintains an audit trail.**

Built for Razorpay Track 3.

## 1. What problem this solves
Failed payments leak recoverable revenue. A network timeout usually just
needs a retry; a card decline with a strong UPI history usually recovers if
you offer UPI instead; a customer who's abandoned checkout twice should get
a reminder, not a third silent retry. This agent automates that judgment,
inside hard guardrails, and proves how much money it actually recovered.

## 2. Why it matters
The headline number is **₹ recovered vs. a naive baseline** — not model
accuracy. See `evaluation/evaluation_results.json` for the latest run.

## 3. Architecture
```
Payment (Razorpay-schema)
        ↓
Root-Cause Diagnosis (agent/root_cause.py)          -- deterministic
        ↓
Recovery Probability Model (ml/*)                    -- XGBoost
        ↓
Policy / Guardrail Engine (policy/rules.py)          -- sole authority to allow/block
        ↓
Recovery Agent (agent/agent.py)                      -- rule-based or LLM proposal,
        ↓                                                always checked by policy
Tool Execution (agent/tools.py → simulator/simulate.py)
        ↓
Revenue + Audit Metrics (evaluation/*)
```

The core safety property: **the agent (rule-based or LLM) only *proposes* an
action — the policy engine is the only thing that can let it execute.**
`tests/test_pipeline.py::test_agent_never_executes_a_blocked_action` and
`test_opted_out_customer_always_stops` check this directly.

## 4. How to run

```bash
pip install -r requirements.txt

# 1. Build the demo dataset (fixture — see data/README.md for provenance)
python data/build_demo_dataset.py

# 2. Train the recovery-probability model
python ml/train.py

# 3. Run the baseline (naive "retry every failure once")
python evaluation/baseline.py

# 4. Run the full agent evaluation — headline numbers + audit log
python evaluation/run_evaluation.py

# 5. Guardrail unit tests
pytest tests/ policy/policy_tests.py -q

# 6. Dashboard
streamlit run app/dashboard.py
```

Optional: set `ANTHROPIC_API_KEY` (`.env.example`) to let the agent use an
LLM for the action-proposal step (`run_recovery_cycle(row, use_llm=True)`) —
it still goes through the same policy engine either way. Optional: set
`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` to pull real failed payments from
your own account via `data/razorpay_client.py` instead of the demo CSV; the
rest of the pipeline runs unchanged since it normalizes to the same schema.

## 5. Dataset
`data/razorpay_demo_payments.csv` is a **fixture, not live account data** —
this build has no Razorpay merchant account to pull from. Its schema and
every `error_code` / `error_reason` / `error_source` / `error_step` /
`method` value are copied verbatim from Razorpay's public API docs, not
invented. Full provenance and column-by-column sourcing: `data/README.md`.

## 6. Model
`ml/train.py` trains an XGBoost classifier for `P(recovery)` on the demo
dataset. Evaluated on ROC-AUC, PR-AUC, precision/recall, and a calibration
check (actual recovery rate should rise with predicted-probability bucket —
see `ml/metrics.json` → `calibration_buckets`).

## 7. Agent workflow
`agent/agent.py::run_recovery_cycle` — inspect → diagnose → predict →
retrieve relevant policy (RAG, `rag/retriever.py`) → propose action →
check policy → execute → record full step trace. Every step is logged to
`AgentTrace`, which is what the dashboard's "Agent trace" page renders.

## 8. Evaluation
`evaluation/run_evaluation.py::run_recovery_evaluation()` runs the full
agent over every transaction in the dataset and compares it to the
"retry every failure once" baseline in `evaluation/baseline.py`. Outputs
`evaluation/evaluation_results.json` (headline metrics) and
`evaluation/audit_log.csv` (flat, per-transaction decision log).

## 9. ₹ recovered
Latest run (`evaluation/evaluation_results.json`):
run `python evaluation/run_evaluation.py` to regenerate current numbers —
they are **not hardcoded**, they come from executing the pipeline against
`data/razorpay_demo_payments.csv`.

## 10. Limitations
- Dataset is a documented-schema fixture, not live transaction volume —
  real deployment needs the `razorpay_client.py` live path validated against
  an actual account.
- The simulated execution environment (`simulator/simulate.py`) models
  `P(success | action, root_cause)` with hand-specified, documented
  assumptions; it is not a live payment gateway.
- RAG layer uses TF-IDF over ~6 short policy docs (sufficient for this
  scope; swap in FAISS/Chroma for a larger policy corpus).
- LLM action-proposal path is optional and falls back to the deterministic
  rule-based proposer if no API key is set — the policy engine's guarantees
  hold either way.

## Project layout
```
ai-revenue-recovery/
├── agent/            root-cause diagnosis, tool wrappers, the agent loop
├── app/               dashboard.py — Streamlit UI (4 pages)
├── data/              dataset builder, live-Razorpay-account reader, CSV
├── docs/              product-spec.md
├── evaluation/        baseline.py, run_evaluation.py, results, audit log
├── ml/                features.py, train.py, predict.py, model.pkl
├── policy/            rules.py (guardrail engine) + policy_tests.py
├── rag/               retriever.py + policy_docs/ (retry, cooldown, escalation, ...)
├── simulator/         simulate.py — closed-loop simulated execution
├── tests/             end-to-end pytest smoke tests
├── requirements.txt
└── .env.example
```
