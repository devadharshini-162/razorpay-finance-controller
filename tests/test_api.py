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

    def test_qa_response_quality_without_gemini(self):
        """Test that Q&A produces human-friendly responses when Gemini is disabled."""
        files = {
            "razorpay_file": ("razorpay.csv", _sample_rzp_csv(), "text/csv"),
            "bank_file": ("bank.csv", _sample_bank_csv(), "text/csv"),
        }
        res = client.post("/api/reconcile", files=files, data={"primary_source_name": "razorpay"})
        assert res.status_code == 200
        session_id = res.json()["session_id"]

        # Test resolution summary question
        qa_res = client.post(
            "/api/qa/ask",
            json={"session_id": session_id, "question": "How many transactions were matched?"},
        )
        assert qa_res.status_code == 200
        answer = qa_res.json()["answer"]
        # Should NOT contain JSON or "Verified Facts" - should be human-friendly
        assert "Verified Facts" not in answer
        assert "{" not in answer or "%" in answer  # If curly braces, should be part of output, not JSON
        assert any(word in answer.lower() for word in ["matched", "out of", "resolution"])

    def test_qa_fee_total_question(self):
        """Test Q&A for fee total question without Gemini."""
        files = {
            "razorpay_file": ("razorpay.csv", _sample_rzp_csv(), "text/csv"),
            "bank_file": ("bank.csv", _sample_bank_csv(), "text/csv"),
        }
        res = client.post("/api/reconcile", files=files, data={"primary_source_name": "razorpay"})
        assert res.status_code == 200
        session_id = res.json()["session_id"]

        qa_res = client.post(
            "/api/qa/ask",
            json={"session_id": session_id, "question": "How much fee was deducted?"},
        )
        assert qa_res.status_code == 200
        answer = qa_res.json()["answer"]
        # Should contain currency symbol or word "fee" or "total"
        assert any(word in answer.lower() for word in ["fee", "total", "₹", "deducted"])
        assert "Verified Facts" not in answer

    def test_qa_unresolved_records_question(self):
        """Test Q&A for unresolved records without Gemini."""
        files = {
            "razorpay_file": ("razorpay.csv", _sample_rzp_csv(), "text/csv"),
            "bank_file": ("bank.csv", _sample_bank_csv(), "text/csv"),
        }
        res = client.post("/api/reconcile", files=files, data={"primary_source_name": "razorpay"})
        assert res.status_code == 200
        session_id = res.json()["session_id"]

        qa_res = client.post(
            "/api/qa/ask",
            json={"session_id": session_id, "question": "What are the unresolved transactions?"},
        )
        assert qa_res.status_code == 200
        answer = qa_res.json()["answer"]
        # Should be human-readable
        assert "Verified Facts" not in answer
        # Should contain answer about unresolved/ambiguous/unmatched
        assert any(word in answer.lower() for word in ["unresolved", "ambiguous", "unmatched", "total"])
