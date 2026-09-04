import io
import csv
from datetime import date
from decimal import Decimal
import pytest

from app.models.canonical import CanonicalTransaction
from app.services.reconciliation import FinalReconciliationResult
from app.services.report import ReconciliationReport
from app.services.qa import FinanceQA, GroundedAnswer
from app.ui_app import run_pipeline, parse_uploaded_csv


class DummyFile:
    def __init__(self, name: str, content: str):
        self.name = name
        self._content = content.encode("utf-8")

    def getvalue(self):
        return self._content


def _sample_rzp_csv():
    return (
        "Settlement Ref,Order Reference,Gross,Processing Fee,GST,Settled Amount,Settlement Date,UTR\n"
        "set_1001,order_1001,1000.00,18.00,3.24,978.76,2026-09-01,UTR1001\n"
    )

def _sample_bank_csv():
    return (
        "Txn ID,Txn Date,Narration,Credit,Debit,Bank Ref,Running Balance\n"
        "tx_1001,2026-09-01,Razorpay Settlement UTR1001,978.76,0.00,UTR1001,100000.00\n"
    )

def _sample_ledger_csv():
    return (
        "Invoice No,Paid On,Customer,Amount Received,Remarks\n"
        "INV-1001,2026-09-01,Acme Corp,978.76,UTR1001\n"
    )

def _sample_fourth_csv():
    return (
        "Payout No,Created At,Effective Date,Gross Sales,Processing Charges,GST,Net Payout,External Ref,Beneficiary,Narrative,Payout Channel\n"
        "PO-800001,2026-09-01 10:01:00,2026-09-01,1000.00,18.00,3.24,978.76,UTR1001,Acme Store,Payout PO-800001,NEFT-FAST\n"
    )


class TestUIOrchestration:

    def test_parse_uploaded_csv(self):
        f = DummyFile("test.csv", _sample_rzp_csv())
        rows, cols = parse_uploaded_csv(f)
        assert len(rows) == 1
        assert "Settlement Ref" in cols
        assert rows[0]["Settlement Ref"] == "set_1001"

    def test_run_pipeline_success(self):
        rzp_f = DummyFile("rzp.csv", _sample_rzp_csv())
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        res = run_pipeline(rzp_f, bank_f)
        assert res is not None
        assert isinstance(res["result"], FinalReconciliationResult)
        assert isinstance(res["report"], ReconciliationReport)
        assert isinstance(res["qa_engine"], FinanceQA)

        # Check reconciliation metrics
        report = res["report"]
        assert report.total_source_records == 1
        assert report.deterministic_matches == 1

    def test_run_pipeline_invalid_file(self):
        invalid_f = DummyFile("invalid.csv", "")
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        res = run_pipeline(invalid_f, bank_f)
        assert res is None

    def test_missing_mandatory_source(self):
        rzp_f = DummyFile("rzp.csv", _sample_rzp_csv())
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        # Missing bank target file
        assert run_pipeline(razorpay_file=rzp_f, bank_file=None) is None
        # Missing all merchant source files
        assert run_pipeline(bank_file=bank_f) is None

    def test_optional_ledger_contract(self):
        ledger_f = DummyFile("ledger.csv", _sample_ledger_csv())
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        res = run_pipeline(bank_file=bank_f, ledger_file=ledger_f, primary_source_name="merchant_ledger")
        assert res is not None
        assert res["active_source_name"] == "merchant_ledger"
        assert len(res["source_records"]) == 1
        assert res["source_records"][0].source == "merchant_ledger"

    def test_fourth_source_contract(self):
        fourth_f = DummyFile("fourth.csv", _sample_fourth_csv())
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        res = run_pipeline(bank_file=bank_f, fourth_file=fourth_f, primary_source_name="fourth_source")
        assert res is not None
        assert res["active_source_name"] == "fourth_source"
        assert len(res["source_records"]) == 1
        assert res["source_records"][0].source == "fourth_source"

    def test_qa_invocation_through_ui_pipeline(self):
        rzp_f = DummyFile("rzp.csv", _sample_rzp_csv())
        bank_f = DummyFile("bank.csv", _sample_bank_csv())

        res = run_pipeline(rzp_f, bank_f)
        qa = res["qa_engine"]
        ans = qa.ask("How many transactions were matched?")
        assert isinstance(ans, GroundedAnswer)
        assert ans.evidence.get("facts", {}).get("total_source_records") == 1
