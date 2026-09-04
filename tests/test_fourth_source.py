import csv
import subprocess
from datetime import date
from decimal import Decimal
import pytest

from app.models.canonical import CanonicalTransaction
from app.services.schema_mapper import SchemaMapper, MockLLMProvider
from app.services.normalizer import Normalizer
from app.services.matcher import DeterministicMatcher
from app.services.reconciliation import reconcile, FinalReconciliationResult
from app.services.report import generate_reconciliation_report
from app.services.qa import FinanceQA


class TestFourthSourceMappingAndNormalization:

    def test_schema_mapping_fourth_source(self):
        mapper = SchemaMapper(MockLLMProvider())
        columns = [
            "Payout No", "Created At", "Effective Date", "Gross Sales",
            "Processing Charges", "GST", "Net Payout", "External Ref",
            "Beneficiary", "Narrative", "Payout Channel"
        ]
        res = mapper.map_source("fourth_source", columns, [])

        assert res.column_mapping["Payout No"] == "settlement_id"
        assert res.column_mapping["Created At"] == "transaction_date"
        assert res.column_mapping["Effective Date"] == "settlement_date"
        assert res.column_mapping["Gross Sales"] == "gross_amount"
        assert res.column_mapping["Processing Charges"] == "fee"
        assert res.column_mapping["GST"] == "tax"
        assert res.column_mapping["Net Payout"] == "amount"
        assert res.column_mapping["External Ref"] == "reference"
        assert res.column_mapping["Beneficiary"] == "counterparty"
        assert res.column_mapping["Narrative"] == "description"
        assert "Payout Channel" in res.unmapped_columns

    def test_normalization_and_metadata_escape_hatch(self):
        mapper = SchemaMapper(MockLLMProvider())
        norm = Normalizer()

        raw_row = {
            "Payout No": "PO-800001",
            "Created At": "2026-09-01 10:01:00",
            "Effective Date": "2026-09-01",
            "Gross Sales": "1000.00",
            "Processing Charges": "18.00",
            "GST": "3.24",
            "Net Payout": "978.76",
            "External Ref": "UTR100200",
            "Beneficiary": "Merchant Store 1",
            "Narrative": "Merchant payout PO-800001",
            "Payout Channel": "NEFT-FAST"
        }

        columns = list(raw_row.keys())
        mapping = mapper.map_source("fourth_source", columns, [raw_row])
        txs = norm.normalize([raw_row], mapping)

        assert len(txs) == 1
        tx = txs[0]
        assert isinstance(tx, CanonicalTransaction)
        assert tx.source == "fourth_source"
        assert tx.settlement_id == "PO-800001"
        assert tx.transaction_date == date(2026, 9, 1)
        assert tx.settlement_date == date(2026, 9, 1)
        assert tx.gross_amount == Decimal("1000.00")
        assert tx.fee == Decimal("18.00")
        assert tx.tax == Decimal("3.24")
        assert tx.amount == Decimal("978.76")
        assert tx.reference == "UTR100200"
        assert tx.counterparty == "Merchant Store 1"
        assert tx.description == "Merchant payout PO-800001"
        
        # Test metadata escape hatch
        assert tx.metadata.get("Payout Channel") == "NEFT-FAST"


class TestFourthSourceReconciliationPipeline:

    @pytest.fixture(autouse=True, scope="class")
    def generate_data(self):
        subprocess.run(["python3", "scripts/generate_data.py"], check=True, capture_output=True)

    def _load_all(self):
        mapper = SchemaMapper(MockLLMProvider())
        norm = Normalizer()

        def load(path, source):
            with open(path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                cols = reader.fieldnames
            mapping = mapper.map_source(source, cols, [])
            return norm.normalize(rows, mapping)

        rzp = load("data/raw/razorpay_settlements.csv", "razorpay")
        bank = load("data/raw/bank_statement.csv", "bank")
        fourth = load("data/raw/fourth_source.csv", "fourth_source")
        return rzp, bank, fourth

    def test_fourth_source_reconciliation(self):
        rzp, bank, fourth = self._load_all()

        # Reconcile fourth source against bank using standard pipeline
        result = reconcile(fourth, bank)
        assert isinstance(result, FinalReconciliationResult)
        assert len(result.decisions) == len(fourth)

        # Generate report without fourth-source specific report logic
        report = generate_reconciliation_report(result)
        assert report.total_source_records == len(fourth)
        assert report.overall_resolved_records > 0

    def test_fourth_source_qa_integration(self):
        rzp, bank, fourth = self._load_all()
        result = reconcile(fourth, bank)
        qa = FinanceQA(result, fourth)

        ans = qa.ask("How many transactions were matched?")
        assert ans.evidence.get("facts", {}).get("total_source_records") == len(fourth)

        ans_ref = qa.ask("What is the status of UTR700001?")
        # Grounded answer or refusal if ref doesn't match
        assert "answer" in ans_ref.model_dump()


class TestArchitecturalPurity:

    def test_no_fourth_source_branching_in_core(self):
        """Verify that core service modules contain no source-specific hacks for fourth_source."""
        import inspect
        import app.services.matcher as matcher_mod
        import app.services.report as report_mod
        import app.services.qa as qa_mod

        for mod in (matcher_mod, report_mod, qa_mod):
            source_code = inspect.getsource(mod)
            assert "fourth_source" not in source_code, f"Source-specific branch found in {mod.__name__}"
