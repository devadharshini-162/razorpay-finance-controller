"""
Tests for Milestone 6 — Match-Rate Reporting & Metric Definition.

Verifies:
    - Denominator is Razorpay source records (= number of decisions)
    - Deterministic vs LLM-resolved distinction
    - No double-counting
    - Batch, duplicate, missing, refund handling
    - Resolution rate + unresolved rate ≈ 100%
    - Traceability via record-ID lists
    - Read-only: generating a report does not mutate the result
    - Zero-record edge case
    - Real generated dataset metrics
"""

import copy
import csv
import subprocess
from datetime import date
from decimal import Decimal

import pytest

from app.models.canonical import (
    AuditRecord,
    CanonicalTransaction,
    ExceptionRecord,
    ReconciliationDecision,
)
from app.services.arbitration_provider import MockArbitrationProvider
from app.services.arbitrator import LLMArbitrationService
from app.services.matcher import DeterministicMatcher
from app.services.normalizer import Normalizer
from app.services.reconciliation import FinalReconciliationResult, reconcile
from app.services.report import ReconciliationReport, generate_reconciliation_report
from app.services.schema_mapper import MockLLMProvider, SchemaMapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rzp(record_id="rzp_001", amount="1000.00", ref=None,
         dt=date(2026, 9, 1), gross=None, fee=None, tax=None,
         settlement_id=None, transaction_type="payment"):
    return CanonicalTransaction(
        record_id=record_id, source="razorpay",
        transaction_type=transaction_type,
        amount=Decimal(amount) if amount else None,
        gross_amount=Decimal(gross) if gross else None,
        fee=Decimal(fee) if fee else None,
        tax=Decimal(tax) if tax else None,
        reference=ref,
        settlement_id=settlement_id or record_id,
        settlement_date=dt,
    )

def _bank(record_id="bank_001", amount="1000.00", ref=None,
          dt=date(2026, 9, 1)):
    return CanonicalTransaction(
        record_id=record_id, source="bank",
        transaction_type="unknown",
        amount=Decimal(amount) if amount else None,
        reference=ref, posted_date=dt,
    )


def _make_result(decisions, exceptions=None):
    """Build a FinalReconciliationResult from decision specs."""
    return FinalReconciliationResult(
        decisions=decisions,
        exceptions=exceptions or [],
        audit_records=[],
    )


def _dec(src_id, decision, method, candidate_id=None, evidence=None):
    return ReconciliationDecision(
        decision_id=f"d_{src_id}",
        source_record_id=src_id,
        candidate_record_id=candidate_id,
        decision=decision,
        method=method,
        confidence=0.9 if decision == "matched" else 0.4,
        reason="test",
        evidence=evidence or {},
    )


# ═══════════════════════════════════════════════════════════════════════════
# METRIC CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════


class TestMetricCorrectness:

    def test_total_source_records(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "unmatched", "unmatched"),
            _dec("s3", "ambiguous", "ambiguous"),
        ])
        report = generate_reconciliation_report(result)
        assert report.total_source_records == 3

    def test_deterministic_matches_counted(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "exact_amount_date", "b2"),
            _dec("s3", "matched", "batch_amount_reconciliation", "b3"),
        ])
        report = generate_reconciliation_report(result)
        assert report.deterministic_matches == 3

    def test_llm_resolved_counted(self):
        result = _make_result([
            _dec("s1", "matched", "llm_arbitration", "b1"),
        ])
        report = generate_reconciliation_report(result)
        assert report.llm_resolved_matches == 1
        assert report.deterministic_matches == 0

    def test_ambiguous_counted(self):
        result = _make_result([
            _dec("s1", "ambiguous", "ambiguous"),
            _dec("s2", "ambiguous", "duplicate"),
        ])
        report = generate_reconciliation_report(result)
        assert report.ambiguous_records == 2

    def test_unmatched_counted(self):
        result = _make_result([
            _dec("s1", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert report.unmatched_records == 1

    def test_overall_resolved_equals_det_plus_llm(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "llm_arbitration", "b2"),
            _dec("s3", "ambiguous", "ambiguous"),
            _dec("s4", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert report.overall_resolved_records == 2
        assert report.overall_resolved_records == (
            report.deterministic_matches + report.llm_resolved_matches
        )

    def test_resolution_rate(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "llm_arbitration", "b2"),
            _dec("s3", "ambiguous", "ambiguous"),
            _dec("s4", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert report.overall_resolution_rate == pytest.approx(50.0)

    def test_unresolved_rate(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert report.unresolved_rate == pytest.approx(50.0)

    def test_resolution_plus_unresolved_equals_100(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "llm_arbitration", "b2"),
            _dec("s3", "ambiguous", "ambiguous"),
            _dec("s4", "unmatched", "unmatched"),
            _dec("s5", "matched", "refund_identifier", "b5"),
        ])
        report = generate_reconciliation_report(result)
        assert report.overall_resolution_rate + report.unresolved_rate == pytest.approx(100.0)


# ═══════════════════════════════════════════════════════════════════════════
# NO DOUBLE COUNTING
# ═══════════════════════════════════════════════════════════════════════════


class TestNoDoubleCounting:

    def test_llm_resolved_not_counted_as_deterministic(self):
        result = _make_result([
            _dec("s1", "matched", "llm_arbitration", "b1"),
        ])
        report = generate_reconciliation_report(result)
        assert report.deterministic_matches == 0
        assert report.llm_resolved_matches == 1

    def test_ambiguous_llm_not_counted_as_resolved(self):
        """LLM returned ambiguous → still ambiguous, not resolved."""
        result = _make_result([
            _dec("s1", "ambiguous", "llm_arbitration"),
        ])
        report = generate_reconciliation_report(result)
        assert report.llm_resolved_matches == 0
        assert report.ambiguous_records == 1
        assert report.overall_resolved_records == 0


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES: batch, missing, duplicate, refund
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_batch_counts_source_records(self):
        """3 batch source records → 3 in denominator, 3 resolved."""
        result = _make_result([
            _dec("s1", "matched", "batch_amount_reconciliation", "b1"),
            _dec("s2", "matched", "batch_amount_reconciliation", "b1"),
            _dec("s3", "matched", "batch_amount_reconciliation", "b1"),
        ])
        report = generate_reconciliation_report(result)
        assert report.total_source_records == 3
        assert report.deterministic_matches == 3

    def test_missing_bank_remains_in_denominator(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert report.total_source_records == 2  # not 1

    def test_duplicate_follows_final_decision(self):
        result = _make_result([
            _dec("s1", "ambiguous", "duplicate"),
        ])
        report = generate_reconciliation_report(result)
        assert report.ambiguous_records == 1
        assert report.unmatched_records == 0

    def test_refund_follows_final_decision(self):
        result = _make_result([
            _dec("s1", "matched", "refund_identifier", "b1"),
        ])
        report = generate_reconciliation_report(result)
        assert report.deterministic_matches == 1

    def test_zero_records_no_division_error(self):
        result = _make_result([])
        report = generate_reconciliation_report(result)
        assert report.total_source_records == 0
        assert report.overall_resolution_rate == 0.0
        assert report.unresolved_rate == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# TRACEABILITY
# ═══════════════════════════════════════════════════════════════════════════


class TestTraceability:

    def test_record_id_lists_match_counts(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "llm_arbitration", "b2"),
            _dec("s3", "ambiguous", "ambiguous"),
            _dec("s4", "unmatched", "unmatched"),
        ])
        report = generate_reconciliation_report(result)
        assert len(report.deterministic_match_ids) == report.deterministic_matches
        assert len(report.llm_resolved_ids) == report.llm_resolved_matches
        assert len(report.ambiguous_ids) == report.ambiguous_records
        assert len(report.unmatched_ids) == report.unmatched_records

    def test_specific_ids_are_correct(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "llm_arbitration", "b2"),
            _dec("s3", "ambiguous", "ambiguous"),
        ])
        report = generate_reconciliation_report(result)
        assert "s1" in report.deterministic_match_ids
        assert "s2" in report.llm_resolved_ids
        assert "s3" in report.ambiguous_ids

    def test_method_breakdown(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "matched", "exact_identifier", "b2"),
            _dec("s3", "matched", "exact_amount_date", "b3"),
        ])
        report = generate_reconciliation_report(result)
        assert report.deterministic_method_breakdown == {
            "exact_identifier": 2,
            "exact_amount_date": 1,
        }


# ═══════════════════════════════════════════════════════════════════════════
# READ-ONLY BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════


class TestReadOnly:

    def test_report_does_not_mutate_decisions(self):
        decisions = [
            _dec("s1", "matched", "exact_identifier", "b1"),
            _dec("s2", "ambiguous", "ambiguous"),
        ]
        result = _make_result(decisions)
        snapshot = copy.deepcopy(decisions)

        generate_reconciliation_report(result)

        for orig, snap in zip(decisions, snapshot):
            assert orig.decision == snap.decision
            assert orig.method == snap.method
            assert orig.candidate_record_id == snap.candidate_record_id
            assert orig.confidence == snap.confidence

    def test_report_does_not_mutate_exceptions(self):
        exc = ExceptionRecord(
            exception_id="exc1", record_id="s1",
            category="ambiguous_match", severity="medium",
            reason="Test", confidence=0.4,
            evidence={"candidate_record_ids": ["b1", "b2"]},
        )
        result = _make_result(
            [_dec("s1", "ambiguous", "ambiguous")],
            exceptions=[exc],
        )
        snapshot = copy.deepcopy(exc)

        generate_reconciliation_report(result)

        assert exc.evidence == snapshot.evidence
        assert exc.category == snapshot.category


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPTION SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptionSummary:

    def test_exception_counts(self):
        excs = [
            ExceptionRecord(exception_id="e1", record_id="s1",
                            category="ambiguous_match", severity="medium",
                            reason="test", confidence=0.4),
            ExceptionRecord(exception_id="e2", record_id="s2",
                            category="missing_record", severity="high",
                            reason="test", confidence=0.1),
        ]
        result = _make_result(
            [_dec("s1", "ambiguous", "ambiguous"),
             _dec("s2", "unmatched", "unmatched")],
            exceptions=excs,
        )
        report = generate_reconciliation_report(result)
        assert report.total_exceptions == 2
        assert report.exceptions_by_category == {
            "ambiguous_match": 1,
            "missing_record": 1,
        }
        assert report.high_severity_exceptions == 1

    def test_resolved_exception_distinguished(self):
        """An exception with resolved_by evidence should be counted as resolved."""
        exc = ExceptionRecord(
            exception_id="e1", record_id="s1",
            category="ambiguous_match", severity="medium",
            reason="test", confidence=0.4,
            evidence={"resolved_by": "llm_arbitration"},
        )
        result = _make_result(
            [_dec("s1", "matched", "llm_arbitration", "b1")],
            exceptions=[exc],
        )
        report = generate_reconciliation_report(result)
        assert report.resolved_exceptions == 1
        assert report.active_exceptions == 0

    def test_unresolved_exception_counted_as_active(self):
        exc = ExceptionRecord(
            exception_id="e1", record_id="s1",
            category="ambiguous_match", severity="medium",
            reason="test", confidence=0.4,
            evidence={},
        )
        result = _make_result(
            [_dec("s1", "ambiguous", "ambiguous")],
            exceptions=[exc],
        )
        report = generate_reconciliation_report(result)
        assert report.active_exceptions == 1
        assert report.resolved_exceptions == 0


# ═══════════════════════════════════════════════════════════════════════════
# HUMAN-READABLE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


class TestSummaryOutput:

    def test_summary_returns_string(self):
        result = _make_result([
            _dec("s1", "matched", "exact_identifier", "b1"),
        ])
        report = generate_reconciliation_report(result)
        text = report.summary()
        assert isinstance(text, str)
        assert "Reconciliation Summary" in text
        assert "100.0%" in text


# ═══════════════════════════════════════════════════════════════════════════
# REAL GENERATED DATASET
# ═══════════════════════════════════════════════════════════════════════════


class TestRealDataset:
    """Run the reporting layer against the real generated dataset."""

    @pytest.fixture(autouse=True, scope="class")
    def generate_data(self):
        subprocess.run(
            ["python3", "scripts/generate_data.py"],
            check=True, capture_output=True,
        )

    def _load(self):
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
        return rzp, bank

    def test_real_dataset_report(self):
        rzp, bank = self._load()
        result = reconcile(rzp, bank)
        report = generate_reconciliation_report(result)

        # Sanity checks — not hardcoded values, just structural invariants
        assert report.total_source_records == len(rzp)
        assert report.total_source_records > 0
        assert report.overall_resolved_records == (
            report.deterministic_matches + report.llm_resolved_matches
        )
        assert report.overall_resolution_rate + report.unresolved_rate == pytest.approx(100.0)
        assert (
            report.deterministic_matches
            + report.llm_resolved_matches
            + report.ambiguous_records
            + report.unmatched_records
        ) == report.total_source_records

        # Print summary for manual inspection
        print(report.summary())

    def test_real_dataset_with_arbitration(self):
        """Run with mock LLM arbitration that always returns ambiguous."""
        rzp, bank = self._load()
        provider = MockArbitrationProvider(override_response={
            "decision": "ambiguous",
            "candidate_record_id": None,
            "confidence": 0.35,
            "reason": "Cannot distinguish candidates.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(rzp, bank, arb)
        report = generate_reconciliation_report(result)

        # LLM returned ambiguous for everything → no LLM resolutions
        assert report.llm_resolved_matches == 0
        # But pipeline should still have the same total
        assert report.total_source_records == len(rzp)
        assert report.overall_resolution_rate + report.unresolved_rate == pytest.approx(100.0)

        print(report.summary())
