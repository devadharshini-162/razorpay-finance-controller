import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api_app import export_exceptions, export_reconciliation, sessions
from app.models.canonical import CanonicalTransaction, ExceptionRecord, ReconciliationDecision
from app.services.reconciliation import FinalReconciliationResult


def _session_id() -> str:
    session_id = "export-test-session"
    source = CanonicalTransaction(
        record_id="source-1", source="razorpay", transaction_type="settlement",
        amount=Decimal("100.00"), transaction_date=date(2026, 9, 1), reference="SET-1",
    )
    bank = CanonicalTransaction(
        record_id="bank-1", source="bank", transaction_type="settlement",
        amount=Decimal("99.00"), posted_date=date(2026, 9, 2), reference="UTR-1",
    )
    matched = ReconciliationDecision(
        decision_id="decision-1", source_record_id="source-1", candidate_record_id="bank-1",
        decision="matched", method="reference", confidence=1.0, reason="Reference matched.",
    )
    ambiguous = ReconciliationDecision(
        decision_id="decision-2", source_record_id="source-2", candidate_record_id="bank-1",
        decision="ambiguous", method="amount_date", confidence=0.5, reason="Multiple candidates.",
    )
    exception = ExceptionRecord(
        exception_id="exception-1", record_id="source-2", category="ambiguous_match",
        severity="high", reason="Multiple candidates.", confidence=0.5,
        evidence={"candidates": ["bank-1"], "amount": Decimal("100.00")},
    )
    sessions[session_id] = {
        "result": FinalReconciliationResult(decisions=[matched, ambiguous], exceptions=[exception]),
        "source_records": [source], "target_records": [bank],
    }
    return session_id


def test_reconciliation_csv_export_has_normalized_rows():
    response = export_reconciliation(_session_id(), "csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.body.decode("utf-8-sig"))))
    assert response.headers["content-type"].startswith("text/csv")
    assert len(rows) == 2
    assert rows[0]["Status"] == "Matched"
    assert rows[0]["Bank Record ID"] == "bank-1"
    assert rows[0]["Amount Difference"] == "1.00"
    assert rows[1]["Status"] == "Ambiguous"
    assert rows[1]["Bank Record ID"] == ""


def test_reconciliation_xlsx_export_has_headers():
    response = export_reconciliation(_session_id(), "xlsx")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.body)) as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
    assert "Decision ID" in sheet
    assert "Source Amount" in sheet


def test_exception_csv_and_xlsx_exports_preserve_open_exception():
    session_id = _session_id()
    csv_response = export_exceptions(session_id, "csv")
    rows = list(csv.DictReader(io.StringIO(csv_response.body.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["Status"] == "Open"
    assert rows[0]["Exception Category"] == "ambiguous_match"
    assert rows[0]["Severity"] == "high"
    assert rows[0]["Reason"] == "Multiple candidates."
    assert '"candidates"' in rows[0]["Evidence"]
    assert "Review the candidate records" in rows[0]["Suggested Action"]
    xlsx_response = export_exceptions(session_id, "xlsx")
    assert xlsx_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(xlsx_response.body)) as workbook:
        assert "Exception Category" in workbook.read("xl/worksheets/sheet1.xml").decode()


def test_export_errors_and_empty_results():
    with pytest.raises(HTTPException) as missing:
        export_reconciliation("missing", "csv")
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as invalid:
        export_reconciliation(_session_id(), "pdf")
    assert invalid.value.status_code == 400
    sessions["empty-export-session"] = {
        "result": FinalReconciliationResult(), "source_records": [], "target_records": [],
    }
    response = export_exceptions("empty-export-session", "csv")
    assert response.status_code == 200
    assert response.body.decode("utf-8-sig").strip().split(",")[0] == "Exception ID"
