import sys
import os

# Ensure workspace root is in sys.path for direct `streamlit run app/ui_app.py` execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import csv
import io
import os
import streamlit as st
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

from app.services.schema_mapper import SchemaMapper, MockLLMProvider
from app.services.normalizer import Normalizer

from app.services.reconciliation import reconcile, FinalReconciliationResult
from app.services.report import generate_reconciliation_report, ReconciliationReport
from app.services.qa import FinanceQA
from app.services.arbitrator import LLMArbitrationService

from app.services.arbitration_provider import MockArbitrationProvider
from app.services.gemini_providers import GeminiLLMProvider, GeminiArbitrationProvider, gemini_qa_provider_func


# ---------------------------------------------------------------------------
# Helper Pipeline Functions (Pure Logic & Orchestration, Importable by Tests)
# ---------------------------------------------------------------------------
def parse_uploaded_csv(uploaded_file):
    """Parse a Streamlit, FastAPI, or Dummy UploadedFile object into raw list of dicts."""
    try:
        if hasattr(uploaded_file, "file"):
            uploaded_file.file.seek(0)
            raw_data = uploaded_file.file.read()
            content = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
        elif hasattr(uploaded_file, "getvalue"):
            raw_data = uploaded_file.getvalue()
            content = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
        elif hasattr(uploaded_file, "read"):
            raw_data = uploaded_file.read()
            content = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
        else:
            return None, None

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        fieldnames = reader.fieldnames or []
        return rows, fieldnames
    except Exception:
        return None, None


def run_pipeline(razorpay_file=None, bank_file=None, ledger_file=None, fourth_file=None, primary_source_name="razorpay"):
    """Orchestrates existing backend services without modifying semantics."""
    
    gemini_enabled = os.environ.get("GEMINI_ENABLED", "false").lower() == "true"
    api_key_present = bool(os.environ.get("GEMINI_API_KEY"))
    
    if gemini_enabled and api_key_present:
        print("[System] Running in GEMINI-ENABLED mode.")
        llm_provider = GeminiLLMProvider()
        arbitration_provider = GeminiArbitrationProvider()
        qa_provider_func = gemini_qa_provider_func
    else:
        print("[System] Running in DETERMINISTIC mode.")
        llm_provider = MockLLMProvider()
        arbitration_provider = MockArbitrationProvider()
        qa_provider_func = None
        
    mapper = SchemaMapper(llm_provider)
    normalizer = Normalizer()

    parsed_sources = {}

    # 1. Parse & Normalize Razorpay
    if razorpay_file is not None:
        rzp_rows, rzp_cols = parse_uploaded_csv(razorpay_file)
        if rzp_rows:
            rzp_mapping = mapper.map_source("razorpay", rzp_cols, rzp_rows[:5])
            parsed_sources["razorpay"] = normalizer.normalize(rzp_rows, rzp_mapping)

    # 2. Parse & Normalize Bank Statement (Mandatory Target)
    if bank_file is None:
        return None
    bank_rows, bank_cols = parse_uploaded_csv(bank_file)
    if not bank_rows:
        return None
    bank_mapping = mapper.map_source("bank", bank_cols, bank_rows[:5])
    target_records = normalizer.normalize(bank_rows, bank_mapping)

    # 3. Optional Merchant Ledger
    if ledger_file is not None:
        ledg_rows, ledg_cols = parse_uploaded_csv(ledger_file)
        if ledg_rows:
            ledg_mapping = mapper.map_source("merchant_ledger", ledg_cols, ledg_rows[:5])
            parsed_sources["merchant_ledger"] = normalizer.normalize(ledg_rows, ledg_mapping)

    # 4. Optional Fourth Source
    if fourth_file is not None:
        fourth_rows, fourth_cols = parse_uploaded_csv(fourth_file)
        if fourth_rows:
            fourth_mapping = mapper.map_source("fourth_source", fourth_cols, fourth_rows[:5])
            parsed_sources["fourth_source"] = normalizer.normalize(fourth_rows, fourth_mapping)

    # Determine primary source_records based on exact backend reconcile contract
    if primary_source_name in parsed_sources:
        source_records = parsed_sources[primary_source_name]
    elif parsed_sources:
        primary_source_name = list(parsed_sources.keys())[0]
        source_records = parsed_sources[primary_source_name]
    else:
        return None

    # 5. Execute Deterministic Reconciliation
    # Arbitration is injected conditionally. If purely deterministic rules are required, it gets None.
    # Here, to test the Gemini capabilities while degrading gracefully, we wire the arbitrator.
    if gemini_enabled and api_key_present:
        arbitrator = LLMArbitrationService(provider=arbitration_provider)
    else:
        arbitrator = None
        
    result = reconcile(source_records, target_records, arbitrator=arbitrator)

    # 6. Generate Report
    report = generate_reconciliation_report(result)

    # 7. Initialize Q&A Engine
    qa_engine = FinanceQA(result, source_records, provider_func=qa_provider_func)

    return {
        "result": result,
        "report": report,
        "qa_engine": qa_engine,
        "source_records": source_records,
        "target_records": target_records,
        "active_source_name": primary_source_name,
    }


def main():
    """Main Streamlit execution block."""
    st.set_page_config(
        page_title="Razorpay AI Finance Controller",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .main {
            background-color: #0f172a;
            color: #f8fafc;
        }
        .metric-card {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 10px 20px;
            border-radius: 8px;
            background-color: #1e293b;
            border: 1px solid #334155;
        }
        .stTabs [aria-selected="true"] {
            background-color: #2563eb !important;
            color: white !important;
            border-color: #3b82f6 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.title("⚡ AI Finance Controller")
    st.sidebar.markdown("---")
    st.sidebar.subheader("📁 Upload Source Data")

    rzp_file = st.sidebar.file_uploader(
        "Razorpay Settlements (Mandatory)", type=["csv"], key="rzp_upload"
    )
    bank_file = st.sidebar.file_uploader(
        "Bank Statement (Mandatory)", type=["csv"], key="bank_upload"
    )
    ledger_file = st.sidebar.file_uploader(
        "Merchant Ledger (Optional)", type=["csv"], key="ledger_upload"
    )
    fourth_file = st.sidebar.file_uploader(
        "Surprise 4th Source (Optional)", type=["csv"], key="fourth_upload"
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📌 Source Status")

    loaded_status = []
    if rzp_file:
        loaded_status.append(f"✅ Razorpay ({rzp_file.name})")
    else:
        loaded_status.append("❌ Razorpay (Missing)")

    if bank_file:
        loaded_status.append(f"✅ Bank Statement ({bank_file.name})")
    else:
        loaded_status.append("❌ Bank Statement (Missing)")

    if ledger_file:
        loaded_status.append(f"✅ Merchant Ledger ({ledger_file.name})")
    else:
        loaded_status.append("⚪ Merchant Ledger (None)")

    if fourth_file:
        loaded_status.append(f"✅ 4th Source ({fourth_file.name})")
    else:
        loaded_status.append("⚪ 4th Source (None)")

    for status in loaded_status:
        st.sidebar.markdown(status)

    st.sidebar.markdown("---")

    run_button = st.sidebar.button(
        "🚀 Run Reconciliation", type="primary", use_container_width=True
    )

    if run_button:
        if not rzp_file or not bank_file:
            st.sidebar.error("Please upload both Razorpay and Bank Statement CSV files!")
        else:
            with st.spinner("Processing schema mapping, normalization & reconciliation..."):
                res = run_pipeline(rzp_file, bank_file, ledger_file, fourth_file)
                if res:
                    st.session_state["pipeline_data"] = res
                    st.session_state["qa_history"] = []
                    st.sidebar.success("Reconciliation Complete!")

    st.title("Razorpay AI Finance Controller")
    st.caption("Multi-source Financial Reconciliation & Grounded Settlement Q&A")

    if "pipeline_data" not in st.session_state or st.session_state["pipeline_data"] is None:
        st.info("👋 Welcome! Please upload mandatory CSV files in the sidebar and click **Run Reconciliation**.")
        st.stop()

    pipeline = st.session_state["pipeline_data"]
    result: FinalReconciliationResult = pipeline["result"]
    report: ReconciliationReport = pipeline["report"]
    qa_engine: FinanceQA = pipeline["qa_engine"]

    tab_overview, tab_exceptions, tab_decisions, tab_audit, tab_qa = st.tabs(
        [
            "📊 Resolution Overview",
            "⚠️ Exceptions",
            "🔍 Reconciled Decisions",
            "📜 Audit Trail",
            "💬 Grounded Q&A",
        ]
    )

    # TAB 1: Resolution Overview
    with tab_overview:
        st.subheader("Key Reconciliation Metrics")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Source Records", report.total_source_records)
        with col2:
            st.metric("Resolution Rate", f"{report.overall_resolution_rate:.1f}%")
        with col3:
            st.metric("Deterministic Matches", report.deterministic_matches)
        with col4:
            st.metric("LLM-Resolved Matches", report.llm_resolved_matches)

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("Ambiguous Records", report.ambiguous_records)
        with col6:
            st.metric("Unmatched Records", report.unmatched_records)
        with col7:
            st.metric("Total Exceptions", report.total_exceptions)
        with col8:
            st.metric("High Severity Exceptions", report.high_severity_exceptions)

        st.markdown("---")
        st.subheader("Matching Method Breakdown")

        if report.deterministic_method_breakdown:
            breakdown_df = pd.DataFrame(
                list(report.deterministic_method_breakdown.items()),
                columns=["Matching Method", "Record Count"],
            )
            col_chart, col_text = st.columns([2, 1])
            with col_chart:
                st.bar_chart(breakdown_df.set_index("Matching Method"))
            with col_text:
                st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
        else:
            st.write("No deterministic matches produced.")

        with st.expander("📄 Human-Readable Summary Report"):
            st.code(report.summary())

    # TAB 2: Exceptions
    with tab_exceptions:
        st.subheader("Exception Records")

        if not result.exceptions:
            st.success("No exceptions detected in the reconciled dataset.")
        else:
            col_cat, col_sev = st.columns(2)
            with col_cat:
                cats = ["All"] + list(set(e.category for e in result.exceptions))
                selected_cat = st.selectbox("Filter by Category", cats)
            with col_sev:
                sevs = ["All"] + list(set(e.severity for e in result.exceptions))
                selected_sev = st.selectbox("Filter by Severity", sevs)

            filtered_exceptions = result.exceptions
            if selected_cat != "All":
                filtered_exceptions = [e for e in filtered_exceptions if e.category == selected_cat]
            if selected_sev != "All":
                filtered_exceptions = [e for e in filtered_exceptions if e.severity == selected_sev]

            st.caption(f"Showing {len(filtered_exceptions)} of {len(result.exceptions)} exceptions")

            exc_table_data = [
                {
                    "Exception ID": exc.exception_id,
                    "Record ID": exc.record_id,
                    "Category": exc.category,
                    "Severity": exc.severity,
                    "Reason": exc.reason,
                    "Confidence": exc.confidence,
                }
                for exc in filtered_exceptions
            ]

            st.dataframe(pd.DataFrame(exc_table_data), use_container_width=True, hide_index=True)

            st.markdown("### Exception Evidence Inspector")
            selected_exc_id = st.selectbox(
                "Select Exception to View Evidence", [e.exception_id for e in filtered_exceptions]
            )
            if selected_exc_id:
                matching_exc = next(e for e in filtered_exceptions if e.exception_id == selected_exc_id)
                st.write(f"**Reason:** {matching_exc.reason}")
                st.json(matching_exc.evidence)

    # TAB 3: Reconciled Decisions
    with tab_decisions:
        st.subheader("Reconciliation Decisions")

        if not result.decisions:
            st.info("No decisions generated.")
        else:
            col_status, col_search = st.columns([1, 2])
            with col_status:
                statuses = ["All", "matched", "ambiguous", "unmatched"]
                selected_status = st.selectbox("Filter by Decision", statuses)
            with col_search:
                search_query = st.text_input("Search Source/Candidate Record ID")

            filtered_decisions = result.decisions
            if selected_status != "All":
                filtered_decisions = [d for d in filtered_decisions if d.decision == selected_status]
            if search_query:
                q = search_query.lower()
                filtered_decisions = [
                    d
                    for d in filtered_decisions
                    if q in d.source_record_id.lower()
                    or (d.candidate_record_id and q in d.candidate_record_id.lower())
                ]

            st.caption(f"Showing {len(filtered_decisions)} of {len(result.decisions)} decisions")

            dec_table_data = [
                {
                    "Decision ID": dec.decision_id,
                    "Source Record ID": dec.source_record_id,
                    "Candidate Record ID": dec.candidate_record_id or "-",
                    "Decision": dec.decision,
                    "Method": dec.method,
                    "Confidence": dec.confidence,
                    "Reason": dec.reason,
                }
                for dec in filtered_decisions
            ]

            st.dataframe(pd.DataFrame(dec_table_data), use_container_width=True, hide_index=True)

            st.markdown("### Decision Evidence Inspector")
            selected_dec_id = st.selectbox(
                "Select Decision to View Evidence", [d.decision_id for d in filtered_decisions]
            )
            if selected_dec_id:
                matching_dec = next(d for d in filtered_decisions if d.decision_id == selected_dec_id)
                st.write(f"**Reason:** {matching_dec.reason}")
                st.json(matching_dec.evidence)

    # TAB 4: Audit Trail
    with tab_audit:
        st.subheader("Reconciliation Audit Trail")

        if not result.audit_records:
            st.info("No audit records available.")
        else:
            st.caption(f"Total Audit Entries: {len(result.audit_records)}")

            audit_table_data = [
                {
                    "Audit ID": a.audit_id,
                    "Record ID": a.record_id,
                    "Stage": a.stage,
                    "Action": a.action,
                    "Method": a.method,
                    "Decision": a.decision,
                }
                for a in result.audit_records
            ]

            st.dataframe(pd.DataFrame(audit_table_data), use_container_width=True, hide_index=True)

            st.markdown("### Audit Evidence Inspector")
            selected_audit_id = st.selectbox(
                "Select Audit Record to View Evidence", [a.audit_id for a in result.audit_records]
            )
            if selected_audit_id:
                matching_audit = next(a for a in result.audit_records if a.audit_id == selected_audit_id)
                st.write(f"**Stage:** `{matching_audit.stage}` | **Action:** `{matching_audit.action}`")
                st.json(matching_audit.evidence)

    # TAB 5: Grounded Q&A
    with tab_qa:
        st.subheader("Grounded Settlement Q&A")
        st.caption("Ask questions about the reconciled financial dataset. Answers are deterministically grounded.")

        st.markdown("**Sample Questions:**")
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        sample_q = None
        with col_q1:
            if st.button("Match Summary"):
                sample_q = "How many transactions were matched?"
        with col_q2:
            if st.button("Unresolved List"):
                sample_q = "Which records are unresolved?"
        with col_q3:
            if st.button("Total Fees"):
                sample_q = "How much was deducted in fees?"
        with col_q4:
            if st.button("Refunds"):
                sample_q = "Show refunds."

        question_input = st.text_input(
            "Ask a Question", value=sample_q if sample_q else "", placeholder="e.g. Why is razorpay_0054 unresolved?"
        )

        if st.button("Submit Question", type="primary") and question_input.strip():
            with st.spinner("Retrieving facts & phrasing answer..."):
                ans = qa_engine.ask(question_input.strip())
                st.session_state["qa_history"].append((question_input.strip(), ans))

        if st.session_state.get("qa_history"):
            st.markdown("---")
            st.subheader("Q&A History")
            for q_text, ans_obj in reversed(st.session_state["qa_history"]):
                with st.chat_message("user"):
                    st.write(q_text)
                with st.chat_message("assistant"):
                    st.write(ans_obj.answer)
                    if ans_obj.evidence:
                        with st.expander("🔍 Verified Fact & Evidence"):
                            st.json(ans_obj.evidence)


if __name__ == "__main__":
    main()
