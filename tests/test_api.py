import pytest
from fastapi.testclient import TestClient
from app.api_app import app, sessions
from tests.test_ui import _sample_rzp_csv, _sample_bank_csv


client = TestClient(app)


class TestFastAPIAdapter:

    def test_health_check(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "active_sessions" in data

    def test_reconcile_and_qa_flow(self):
        # 1. Reconcile via POST /api/reconcile
        files = {
            "razorpay_file": ("razorpay.csv", _sample_rzp_csv(), "text/csv"),
            "bank_file": ("bank.csv", _sample_bank_csv(), "text/csv"),
        }
        res = client.post("/api/reconcile", files=files, data={"primary_source_name": "razorpay"})
        assert res.status_code == 200
        data = res.json()

        session_id = data.get("session_id")
        assert session_id is not None
        assert data["active_source_name"] == "razorpay"
        assert data["report"]["total_source_records"] == 1
        assert len(data["decisions"]) == 1

        # 2. Get Session via GET /api/session/{session_id}
        sess_res = client.get(f"/api/session/{session_id}")
        assert sess_res.status_code == 200
        assert sess_res.json()["session_id"] == session_id

        # 3. Grounded Q&A via POST /api/qa/ask using session_id
        qa_res = client.post(
            "/api/qa/ask",
            json={"session_id": session_id, "question": "How many transactions were matched?"},
        )
        assert qa_res.status_code == 200
        qa_data = qa_res.json()
        assert "answer" in qa_data
        assert qa_data["evidence"]["facts"]["total_source_records"] == 1

    def test_qa_unauthorized_session(self):
        qa_res = client.post(
            "/api/qa/ask",
            json={"session_id": "invalid-session-uuid", "question": "What is the fee total?"},
        )
        assert qa_res.status_code == 404
        assert "Session not found" in qa_res.json()["detail"]

    def test_reconcile_missing_bank_file(self):
        files = {
            "razorpay_file": ("razorpay.csv", _sample_rzp_csv(), "text/csv"),
        }
        res = client.post("/api/reconcile", files=files)
        assert res.status_code == 400
        assert "Bank statement CSV file is required" in res.json()["detail"]
