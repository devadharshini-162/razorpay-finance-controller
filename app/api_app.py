import uuid
import sys
import os
import csv
import io
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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


def _export_rows(result):
    """Return a spreadsheet-friendly, non-nested reconciliation ledger."""
    return [
        {
            "Decision ID": decision.decision_id,
            "Source Record ID": decision.source_record_id,
            "Bank Record ID": decision.candidate_record_id or "",
            "Decision": decision.decision,
            "Match Method": decision.method,
            "Confidence": decision.confidence,
            "Reason": decision.reason,
        }
        for decision in result.decisions
    ]


def _xlsx_bytes(rows: list[dict]) -> bytes:
    """Create a small standards-compliant XLSX workbook without a new dependency."""
    headers = list(rows[0].keys()) if rows else ["Decision ID"]
    sheet_rows = [headers] + [[row.get(header, "") for header in headers] for row in rows]
    def cell(value, index, row_index):
        ref = f"{chr(65 + index)}{row_index}"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    xml_rows = []
    for row_index, values in enumerate(sheet_rows, 1):
        cells = ''.join(cell(value, index, row_index) for index, value in enumerate(values))
        xml_rows.append(f'<row r="{row_index}">{cells}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Reconciliation" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')
    workbook_rels = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("_rels/.rels", rels)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


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

    try:
        res = run_pipeline(
            razorpay_file=razorpay_file,
            bank_file=bank_file,
            ledger_file=ledger_file,
            fourth_file=fourth_file,
            primary_source_name=primary_source_name,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process the uploaded CSV files: {exc}",
        ) from exc

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
        "llm_mode_enabled": res["llm_mode_enabled"],
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
        "llm_mode_enabled": res["llm_mode_enabled"],
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


@app.get("/api/session/{session_id}/export")
def export_reconciliation(session_id: str, format: str = "csv"):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    if format not in {"csv", "xlsx"}:
        raise HTTPException(status_code=400, detail="format must be csv or xlsx")
    rows = _export_rows(sessions[session_id]["result"])
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else ["Decision ID"])
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=output.getvalue().encode("utf-8-sig"), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="reconciliation-{timestamp}.csv"'},
        )
    return Response(
        content=_xlsx_bytes(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reconciliation-{timestamp}.xlsx"'},
    )


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
