"""
AI Revenue Recovery — Streamlit dashboard.

Run: streamlit run app/dashboard.py

Four pages (matching Day 11 of the plan):
  1. Executive view   - headline ₹ recovered / uplift numbers
  2. Transaction view - pick one failed payment, run it through the agent live
  3. Agent trace       - step-by-step trace of the last transaction you ran
  4. Audit log         - filterable history of every recovery decision
"""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "agent"))
sys.path.append(str(ROOT / "evaluation"))
sys.path.append(str(ROOT / "simulator"))
sys.path.append(str(ROOT / "policy"))
sys.path.append(str(ROOT / "ml"))
sys.path.append(str(ROOT / "rag"))
sys.path.append(str(ROOT / "common"))

from agent import run_recovery_cycle  # noqa: E402
from currency import format_inr  # noqa: E402

DATA_PATH = ROOT / "data" / "razorpay_demo_payments.csv"
RESULTS_PATH = ROOT / "evaluation" / "evaluation_results.json"
AUDIT_LOG_PATH = ROOT / "evaluation" / "audit_log.csv"

st.set_page_config(page_title="AI Revenue Recovery", layout="wide", page_icon="💳")


@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)


@st.cache_data
def load_results():
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text())
    return None


@st.cache_data
def load_audit_log():
    if AUDIT_LOG_PATH.exists():
        return pd.read_csv(AUDIT_LOG_PATH)
    return pd.DataFrame()


rupees = format_inr


df = load_data()
results = load_results()
audit_df = load_audit_log()

st.sidebar.title("💳 AI Revenue Recovery")
page = st.sidebar.radio("View", ["Executive view", "Transaction view", "Agent trace", "Audit log"])
st.sidebar.markdown("---")
st.sidebar.caption(
    "Data source: `data/razorpay_demo_payments.csv` — a fixture built from "
    "Razorpay's documented Payment/Error entity schema, not live account data. "
    "See `data/README.md`."
)

# ---------------------------------------------------------------------------
# Page 1: Executive view
# ---------------------------------------------------------------------------
if page == "Executive view":
    st.title("AI Revenue Recovery")

    if results is None:
        st.warning("No evaluation results yet. Run `python evaluation/run_evaluation.py` first.")
    else:
        s = results["summary"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("₹ at risk", rupees(s["revenue_at_risk_paise"]))
        c2.metric("₹ recovered (AI)", rupees(s["ai_recovered_paise"]),
                   delta=rupees(s["additional_revenue_recovered_paise"]) + " vs baseline")
        c3.metric("Recovery rate", f"{s['ai_recovery_rate']*100:.1f}%",
                   delta=f"{(s['ai_recovery_rate']-s['baseline_recovery_rate'])*100:+.1f} pp vs baseline")
        c4.metric("Recovery uplift", f"{s['recovery_uplift_pct']}%")

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Baseline vs AI agent")
            # Scale + label the axis to whichever unit fits the bigger of
            # the two bars (Cr if >=1 crore, else L) -- same rule as the
            # headline ₹ metrics, so the chart never says "Lakhs" while
            # showing crore-scale numbers.
            max_paise = max(s["baseline_recovered_paise"], s["ai_recovered_paise"])
            use_cr = (max_paise / 100) >= 10_000_000  # >= 1 crore rupees
            divisor = 1e9 if use_cr else 1e7
            unit_label = "Crores" if use_cr else "Lakhs"
            fig = go.Figure(data=[
                go.Bar(name="Recovered", x=["Baseline (retry once)", "AI agent"],
                       y=[s["baseline_recovered_paise"] / divisor, s["ai_recovered_paise"] / divisor],
                       marker_color=["#94a3b8", "#6366f1"]),
            ])
            fig.update_layout(yaxis_title=f"₹ recovered ({unit_label})", showlegend=False, height=380)
            st.plotly_chart(fig, width='stretch')

        with col2:
            st.subheader("Final action distribution")
            actions = s.get("action_distribution", {})
            if actions:
                fig2 = px.pie(names=list(actions.keys()), values=list(actions.values()), hole=0.45)
                fig2.update_layout(height=380)
                st.plotly_chart(fig2, width='stretch')

        st.markdown("---")
        st.subheader("Governance & trust")
        g1, g2, g3 = st.columns(3)
        g1.metric("Policy violations caught & blocked", s["policy_violations_surfaced_and_blocked"])
        g2.metric("Disallowed actions that executed anyway", s["exceeded_retry_limits_that_executed_anyway"],
                   help="Should always be 0 — this is the safety guarantee of the policy layer.")
        g3.metric("Audit coverage", f"{s['audit_coverage']*100:.1f}%")

# ---------------------------------------------------------------------------
# Page 2: Transaction view
# ---------------------------------------------------------------------------
elif page == "Transaction view":
    st.title("Transaction view")
    st.caption("Pick a failed payment and run it live through the full agent loop.")

    txn_id = st.selectbox("Transaction", df["id"].tolist())
    row = df[df["id"] == txn_id].iloc[0].to_dict()

    left, right = st.columns([1, 1])
    with left:
        st.markdown(f"**Transaction:** `{row['id']}`")
        st.markdown(f"**Amount:** {rupees(row['amount'])}")
        st.markdown(f"**Method:** {row['method']}")
        st.markdown(f"**Failure:** {row['error_reason']}  \n*(root cause: {row['root_cause']})*")
        st.markdown(f"**Attempt #:** {row['attempt_number']}")
        st.markdown(f"**UPI history:** {row['upi_success_rate']:.0%}  |  **Card history:** {row['card_success_rate']:.0%}")

        opted_out = st.checkbox("Simulate: customer opted out of recovery contact", value=bool(row.get("opted_out_of_recovery", False)) if "opted_out_of_recovery" in row else False)
        use_llm = st.checkbox("Use LLM for action proposal (falls back to rules if no API key)", value=False)

        if st.button("▶ Run recovery cycle", type="primary"):
            record = run_recovery_cycle(row, use_llm=use_llm, customer_opted_out=opted_out)
            st.session_state["last_record"] = record

    with right:
        record = st.session_state.get("last_record")
        if record:
            st.markdown("### Result")
            st.markdown(f"**Recovery probability:** {record['predicted_probability']*100:.0f}%")
            st.markdown(f"**Proposed action:** `{record['proposed_action']}`")
            badge = "✅ ALLOWED" if record["policy_allowed"] else "⛔ BLOCKED / MODIFIED"
            st.markdown(f"**Policy:** {badge} — {record['policy_reason']}")
            st.markdown(f"**Executed action:** `{record['final_action']}`")
            st.markdown(f"**Outcome:** {record['outcome']}")
            st.markdown(f"**Expected recovery:** {rupees(record['recovered_amount'])}" if record["outcome"] == "SUCCESS" else "**Expected recovery:** ₹0")
            st.info("See the **Agent trace** page for the full step-by-step reasoning.")
        else:
            st.info("Run a transaction to see the agent's decision here.")

# ---------------------------------------------------------------------------
# Page 3: Agent trace
# ---------------------------------------------------------------------------
elif page == "Agent trace":
    st.title("Agent trace")
    record = st.session_state.get("last_record")
    if not record:
        st.info("Run a transaction on the **Transaction view** page first.")
    else:
        st.caption(f"Trace for `{record['transaction_id']}`")
        for i, step in enumerate(record["trace"], start=1):
            with st.expander(f"{i}. {step['step']}", expanded=True):
                st.json(step["detail"])

# ---------------------------------------------------------------------------
# Page 4: Audit log
# ---------------------------------------------------------------------------
elif page == "Audit log":
    st.title("Audit log")
    if audit_df.empty:
        st.warning("No audit log yet. Run `python evaluation/run_evaluation.py` first.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            action_filter = st.multiselect("Final action", sorted(audit_df["final_action"].unique()))
        with col2:
            root_cause_filter = st.multiselect("Root cause", sorted(audit_df["root_cause"].unique()))
        with col3:
            only_violations = st.checkbox("Only show policy violations")

        view = audit_df.copy()
        if action_filter:
            view = view[view["final_action"].isin(action_filter)]
        if root_cause_filter:
            view = view[view["root_cause"].isin(root_cause_filter)]
        if only_violations:
            view = view[view["policy_violations"] != "[]"]

        st.dataframe(view, width='stretch', height=500)
        st.caption(f"{len(view):,} of {len(audit_df):,} transactions shown")
