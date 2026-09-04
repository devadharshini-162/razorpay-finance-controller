import uuid
import sys
import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui_app import run_pipeline
from app.models.canonical import ReconciliationDecision, ExceptionRecord, AuditRecord

app = FastAPI(
    title="Razorpay AI Finance Controller API",
    description="REST API adapter for financial reconciliation engine and grounded Q&A",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store mapping session_id -> pipeline result dict
sessions: dict[str, dict] = {}


class QARequest(BaseModel):
    session_id: str
    question: str


class QAResponse(BaseModel):
    answer: str
    evidence: dict


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Razorpay AI Finance Controller API",
        "active_sessions": len(sessions),
    }


@app.post("/api/reconcile")
async def reconcile_endpoint(
    razorpay_file: Optional[UploadFile] = File(None),
    bank_file: Optional[UploadFile] = File(None),
    ledger_file: Optional[UploadFile] = File(None),
    fourth_file: Optional[UploadFile] = File(None),
    primary_source_name: str = Form("razorpay"),
):
    """Executes multi-source reconciliation pipeline and stores session result."""
    if bank_file is None:
        raise HTTPException(status_code=400, detail="Bank statement CSV file is required.")

    res = run_pipeline(
        razorpay_file=razorpay_file,
        bank_file=bank_file,
        ledger_file=ledger_file,
        fourth_file=fourth_file,
        primary_source_name=primary_source_name,
    )

    if not res:
        raise HTTPException(
            status_code=400,
            detail="Failed to parse files or generate reconciliation result. Please check CSV format.",
        )

    session_id = str(uuid.uuid4())
    sessions[session_id] = res

    result = res["result"]
    report = res["report"]

    return {
        "session_id": session_id,
        "active_source_name": res["active_source_name"],
        "report": {
            "total_source_records": report.total_source_records,
            "overall_resolved_records": report.overall_resolved_records,
            "overall_resolution_rate": report.overall_resolution_rate,
            "overall_unresolved_rate": report.unresolved_rate,
            "deterministic_matches": report.deterministic_matches,
            "llm_resolved_matches": report.llm_resolved_matches,
            "ambiguous_records": report.ambiguous_records,
            "unmatched_records": report.unmatched_records,
            "total_exceptions": report.total_exceptions,
            "high_severity_exceptions": report.high_severity_exceptions,
            "deterministic_method_breakdown": report.deterministic_method_breakdown,
            "summary_text": report.summary(),
        },
        "decisions": [d.model_dump() for d in result.decisions],
        "exceptions": [e.model_dump() for e in result.exceptions],
        "audit_records": [a.model_dump() for a in result.audit_records],
    }


@app.get("/api/session/{session_id}")
def get_session_endpoint(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    res = sessions[session_id]
    result = res["result"]
    report = res["report"]

    return {
        "session_id": session_id,
        "active_source_name": res["active_source_name"],
        "report": {
            "total_source_records": report.total_source_records,
            "overall_resolved_records": report.overall_resolved_records,
            "overall_resolution_rate": report.overall_resolution_rate,
            "overall_unresolved_rate": report.unresolved_rate,
            "deterministic_matches": report.deterministic_matches,
            "llm_resolved_matches": report.llm_resolved_matches,
            "ambiguous_records": report.ambiguous_records,
            "unmatched_records": report.unmatched_records,
            "total_exceptions": report.total_exceptions,
            "high_severity_exceptions": report.high_severity_exceptions,
            "deterministic_method_breakdown": report.deterministic_method_breakdown,
            "summary_text": report.summary(),
        },
        "decisions": [d.model_dump() for d in result.decisions],
        "exceptions": [e.model_dump() for e in result.exceptions],
        "audit_records": [a.model_dump() for a in result.audit_records],
    }


@app.post("/api/qa/ask", response_model=QAResponse)
def qa_ask_endpoint(req: QARequest):
    """Executes grounded Q&A strictly against the session's reconciliation result."""
    if req.session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please run reconciliation first to ground Q&A.",
        )

    session = sessions[req.session_id]
    qa_engine = session["qa_engine"]

    ans = qa_engine.ask(req.question.strip())
    return QAResponse(answer=ans.answer, evidence=ans.evidence)
