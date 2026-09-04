"""
Tests for Milestone 5 — Exception & Audit Integration + Hardening.

Verifies:
    - Every source record has audit coverage
    - Deterministic evidence survives LLM arbitration
    - Exception preservation and resolution marking
    - Batch/duplicate/refund evidence integrity
    - Case J genuinely reaches the ambiguity path
    - FinalReconciliationResult exposes decisions + exceptions + audits
    - No false amount-difference exceptions for valid financial reconciliation
"""

import csv
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.canonical import (
    AuditRecord,
    CanonicalTransaction,
    ExceptionRecord,
    ReconciliationDecision,
)
from app.services.arbitration_provider import MockArbitrationProvider
from app.services.arbitrator import LLMArbitrationService
from app.services.matcher import DeterministicMatcher, MatchResult
from app.services.normalizer import Normalizer
from app.services.reconciliation import FinalReconciliationResult, reconcile
from app.services.schema_mapper import MockLLMProvider, SchemaMapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rzp(
    record_id="rzp_001",
    amount="1000.00",
    ref=None,
    dt=date(2026, 9, 1),
    gross=None,
    fee=None,
    tax=None,
    settlement_id=None,
    transaction_type="payment",
):
    return CanonicalTransaction(
        record_id=record_id,
        source="razorpay",
        transaction_type=transaction_type,
        amount=Decimal(amount) if amount else None,
        gross_amount=Decimal(gross) if gross else None,
        fee=Decimal(fee) if fee else None,
        tax=Decimal(tax) if tax else None,
        reference=ref,
        settlement_id=settlement_id or record_id,
        settlement_date=dt,
    )


def _bank(
    record_id="bank_001",
    amount="1000.00",
    ref=None,
    dt=date(2026, 9, 1),
):
    return CanonicalTransaction(
        record_id=record_id,
        source="bank",
        transaction_type="unknown",
        amount=Decimal(amount) if amount else None,
        reference=ref,
        posted_date=dt,
    )


def _load_dataset():
    """Load the generated synthetic dataset through the real pipeline."""
    mapper = SchemaMapper(MockLLMProvider())
    norm = Normalizer()

    def _load(path, source):
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            cols = reader.fieldnames
        mapping = mapper.map_source(source, cols, [])
        return norm.normalize(rows, mapping)

    rzp_txs = _load("data/raw/razorpay_settlements.csv", "razorpay")
    bank_txs = _load("data/raw/bank_statement.csv", "bank")
    return rzp_txs, bank_txs


def _load_ground_truth():
    with open("data/processed/reconciliation_ground_truth.csv") as f:
        return list(csv.DictReader(f))


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT COVERAGE
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditCoverage:
    """Every reconciled source record must have at least one audit entry."""

    def test_every_source_record_has_audit(self):
        """After full pipeline, no source record is missing an audit trail."""
        src = [
            _rzp(record_id="s1", ref="UTR100"),
            _rzp(record_id="s2", amount="500"),
            _rzp(record_id="s3", amount="999"),
        ]
        tgt = [
            _bank(record_id="b1", ref="UTR100"),
            _bank(record_id="b2", amount="500"),
        ]
        provider = MockArbitrationProvider(override_response={
            "decision": "ambiguous",
            "candidate_record_id": None,
            "confidence": 0.4,
            "reason": "Still ambiguous.",
            "evidence": {},
        })
        arbitrator = LLMArbitrationService(provider)
        result = reconcile(src, tgt, arbitrator)

        audited_ids = {a.record_id for a in result.audit_records}
        for s in src:
            assert s.record_id in audited_ids, (
                f"Source record {s.record_id} has no audit entry"
            )

    def test_audit_identifies_stage_method_decision(self):
        """Each audit record contains meaningful stage / method / decision."""
        src = [_rzp(record_id="s1", ref="UTR200")]
        tgt = [_bank(record_id="b1", ref="UTR200")]
        result = reconcile(src, tgt)

        for audit in result.audit_records:
            assert audit.stage, "audit.stage is empty"
            assert audit.method, "audit.method is empty"
            assert audit.decision, "audit.decision is empty"

    def test_audit_evidence_preserved(self):
        """Audit records carry evidence from the matching step."""
        src = [_rzp(record_id="s1", ref="UTR300")]
        tgt = [_bank(record_id="b1", ref="UTR300")]
        result = reconcile(src, tgt)

        match_audits = [
            a for a in result.audit_records
            if a.record_id == "s1" and a.stage == "deterministic_matching"
        ]
        assert len(match_audits) >= 1
        audit = match_audits[0]
        assert audit.evidence, "Audit evidence should not be empty for a matched record"

    def test_arbitration_adds_audit_without_deleting_deterministic(self):
        """When arbitration runs, it appends an audit entry; det. entries survive."""
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        # Force an ambiguous decision from deterministic, then resolve via LLM
        matcher = DeterministicMatcher()
        det_result = matcher.match(src, tgt)
        assert det_result.decisions[0].decision == "ambiguous"

        det_audit_count = len([
            a for a in det_result.audit_records if a.record_id == "s1"
        ])

        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "b1",
            "confidence": 0.85,
            "reason": "Evidence favors b1.",
            "evidence": {"mock": True},
        })
        arb = LLMArbitrationService(provider)
        arb.process_match_result(det_result, src, tgt)

        all_audits = [a for a in det_result.audit_records if a.record_id == "s1"]
        # Should have the original deterministic audit(s) PLUS one from arbitration
        assert len(all_audits) > det_audit_count
        arb_audits = [a for a in all_audits if a.stage == "llm_arbitration"]
        assert len(arb_audits) == 1
        assert arb_audits[0].method == "llm_arbitration"


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPTION PRESERVATION & RESOLUTION MARKING
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptionPreservation:
    """Exceptions must survive arbitration; resolved ones are marked via evidence."""

    def test_exception_preserved_after_arbitration_match(self):
        """Original ambiguous exception still exists after LLM resolves to matched."""
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        matcher = DeterministicMatcher()
        det_result = matcher.match(src, tgt)
        # Deterministic should produce an exception for ambiguity
        exc_before = [e for e in det_result.exceptions if e.record_id == "s1"]
        assert len(exc_before) >= 1, "Deterministic ambiguity should produce an exception"

        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "b1",
            "confidence": 0.85,
            "reason": "Resolved via evidence.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        arb.process_match_result(det_result, src, tgt)

        exc_after = [e for e in det_result.exceptions if e.record_id == "s1"]
        assert len(exc_after) >= 1, "Exception must NOT be deleted after arbitration"

    def test_resolved_exception_has_resolution_evidence(self):
        """After LLM match, the exception's evidence should contain 'resolved_by'."""
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        matcher = DeterministicMatcher()
        det_result = matcher.match(src, tgt)

        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "b1",
            "confidence": 0.85,
            "reason": "Resolved.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        arb.process_match_result(det_result, src, tgt)

        exc = [e for e in det_result.exceptions if e.record_id == "s1"][0]
        assert exc.evidence.get("resolved_by") == "llm_arbitration", (
            "Resolved exception should be marked via evidence, not deleted"
        )

    def test_unresolved_exception_has_no_resolution_marker(self):
        """If LLM returns ambiguous, the exception should NOT have 'resolved_by'."""
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        matcher = DeterministicMatcher()
        det_result = matcher.match(src, tgt)

        provider = MockArbitrationProvider(override_response={
            "decision": "ambiguous",
            "candidate_record_id": None,
            "confidence": 0.3,
            "reason": "Cannot distinguish.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        arb.process_match_result(det_result, src, tgt)

        exc = [e for e in det_result.exceptions if e.record_id == "s1"][0]
        assert "resolved_by" not in exc.evidence, (
            "Unresolved exception must NOT be marked as resolved"
        )


# ═══════════════════════════════════════════════════════════════════════════
# EVIDENCE CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════


class TestEvidenceCategories:
    """Verify exception categories and evidence for specific case types."""

    def test_ambiguous_produces_ambiguous_match_exception(self):
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        result = reconcile(src, tgt)
        excs = [e for e in result.exceptions if e.record_id == "s1"]
        assert any(e.category == "ambiguous_match" for e in excs)

    def test_missing_record_produces_exception(self):
        src = [_rzp(record_id="s1", amount="99999")]
        tgt = [_bank(record_id="b1", amount="1")]
        result = reconcile(src, tgt)
        excs = [e for e in result.exceptions if e.record_id == "s1"]
        assert any(e.category == "missing_record" for e in excs)

    def test_duplicate_preserves_candidate_ids(self):
        """Duplicate bank records sharing an identifier produce evidence with candidate IDs."""
        src = [_rzp(record_id="s1", ref="SAME_UTR")]
        tgt = [
            _bank(record_id="b1", ref="SAME_UTR", amount="100"),
            _bank(record_id="b2", ref="SAME_UTR", amount="100"),
        ]
        result = reconcile(src, tgt)
        dup_excs = [e for e in result.exceptions if e.category == "duplicate"]
        assert len(dup_excs) >= 1
        exc = dup_excs[0]
        assert "candidate_record_ids" in exc.evidence
        assert set(exc.evidence["candidate_record_ids"]) == {"b1", "b2"}

    def test_batch_preserves_evidence(self):
        """Batch settlement decisions carry source_record_ids and target evidence."""
        s1 = _rzp(record_id="s1", amount="100", ref="BATCH_UTR")
        s2 = _rzp(record_id="s2", amount="200", ref="BATCH_UTR")
        tgt = [_bank(record_id="b1", amount="300", ref="BATCH_UTR")]
        result = reconcile([s1, s2], tgt)

        batch_decisions = [
            d for d in result.decisions
            if d.method == "batch_amount_reconciliation"
        ]
        assert len(batch_decisions) == 2
        for d in batch_decisions:
            assert "source_record_ids" in d.evidence
            assert "target_record_id" in d.evidence

    def test_refund_evidence_distinguishable(self):
        """Refund-related decisions are distinguishable from ordinary payment mismatches."""
        src = [_rzp(
            record_id="s1",
            settlement_id="ref_123",
            amount="500",
            gross="500",
            ref=None,
            transaction_type="refund",
        )]
        tgt = [_bank(record_id="b1", amount="-500")]
        result = reconcile(src, tgt)

        d = result.decisions[0]
        assert d.decision == "matched"
        assert d.method == "refund_identifier"
        assert "razorpay_settlement_id" in d.evidence

    def test_valid_financial_reconciliation_no_false_exception(self):
        """gross - fee - tax = bank credit should NOT produce an amount_difference exception."""
        src = [_rzp(
            record_id="s1",
            amount="9787.60",
            gross="10000",
            fee="180",
            tax="32.40",
        )]
        tgt = [_bank(record_id="b1", amount="9787.60")]
        result = reconcile(src, tgt)

        assert result.decisions[0].decision == "matched"
        amount_diff_excs = [
            e for e in result.exceptions if e.category == "amount_difference"
        ]
        assert len(amount_diff_excs) == 0, (
            "Valid financial reconciliation must NOT produce a false amount_difference exception"
        )


# ═══════════════════════════════════════════════════════════════════════════
# ARBITRATION SAFETY (reinforcement tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestArbitrationSafety:
    """Reinforce trust-boundary tests from M4 in the context of M5 hardening."""

    def test_malformed_llm_cannot_corrupt_decision(self):
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        provider = MockArbitrationProvider(override_response={
            "decision": "GARBAGE",
            "confidence": 999,
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(src, tgt, arb)
        d = result.decisions[0]
        assert d.decision == "ambiguous"

    def test_hallucinated_candidate_rejected(self):
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "bank_NOT_A_REAL_RECORD",
            "confidence": 0.95,
            "reason": "I hallucinated this.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(src, tgt, arb)
        d = result.decisions[0]
        assert d.decision == "ambiguous"
        assert d.candidate_record_id is None

    def test_deterministic_evidence_survives_arbitration(self):
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "b1",
            "confidence": 0.85,
            "reason": "Evidence favors b1.",
            "evidence": {"detail": "counterparty match"},
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(src, tgt, arb)

        d = result.decisions[0]
        assert d.decision == "matched"
        # Original deterministic evidence must survive
        assert "candidate_record_ids" in d.evidence
        assert set(d.evidence["candidate_record_ids"]) == {"b1", "b2"}
        # LLM evidence added alongside
        assert "llm_evidence" in d.evidence

    def test_resolved_match_is_auditable(self):
        src = [_rzp(record_id="s1", amount="100")]
        tgt = [
            _bank(record_id="b1", amount="100"),
            _bank(record_id="b2", amount="100"),
        ]
        provider = MockArbitrationProvider(override_response={
            "decision": "matched",
            "candidate_record_id": "b1",
            "confidence": 0.85,
            "reason": "Resolved.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(src, tgt, arb)

        arb_audits = [
            a for a in result.audit_records
            if a.stage == "llm_arbitration" and a.record_id == "s1"
        ]
        assert len(arb_audits) == 1
        assert arb_audits[0].decision == "matched"
        assert arb_audits[0].method == "llm_arbitration"


# ═══════════════════════════════════════════════════════════════════════════
# FINAL RECONCILIATION RESULT STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════


class TestFinalReconciliationResult:
    """The reconcile() function must return a clean, consumable structure."""

    def test_result_type(self):
        result = reconcile([], [])
        assert isinstance(result, FinalReconciliationResult)

    def test_result_exposes_all_three_collections(self):
        src = [_rzp(record_id="s1", ref="UTR400")]
        tgt = [_bank(record_id="b1", ref="UTR400")]
        result = reconcile(src, tgt)

        assert isinstance(result.decisions, list)
        assert isinstance(result.exceptions, list)
        assert isinstance(result.audit_records, list)
        assert len(result.decisions) == 1

    def test_convenience_accessors(self):
        src = [
            _rzp(record_id="s1", ref="UTR500"),
            _rzp(record_id="s2", amount="999"),
        ]
        tgt = [_bank(record_id="b1", ref="UTR500")]
        result = reconcile(src, tgt)

        assert len(result.matched_decisions) == 1
        assert len(result.unmatched_decisions) == 1
        assert result.match_rate() == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════════════
# CASE J — GENUINE AMBIGUITY THROUGH THE REAL PIPELINE
# ═══════════════════════════════════════════════════════════════════════════


class TestCaseJAmbiguity:
    """Prove Case J reaches the ambiguity path through the real pipeline.

    The ground truth CSV contains records with expected_relationship
    'ambiguous_1' and 'ambiguous_2'. These must produce decision == 'ambiguous'
    from the deterministic matcher.
    """

    @pytest.fixture(autouse=True, scope="class")
    def generate_data(self):
        """Regenerate the dataset to ensure freshness."""
        subprocess.run(
            ["python3", "scripts/generate_data.py"],
            check=True,
            capture_output=True,
        )

    def test_case_j_deterministic_ambiguity(self):
        """Case J source records must be classified as 'ambiguous' by the
        deterministic matcher — NOT resolved via exact_amount_date or any other rule."""
        rzp_txs, bank_txs = _load_dataset()
        gt = _load_ground_truth()

        matcher = DeterministicMatcher()
        result = matcher.match(rzp_txs, bank_txs)
        dec_by_src = {d.source_record_id: d for d in result.decisions}

        # Build settlement_id → canonical record_id mapping
        rzp_by_sid = {tx.settlement_id: tx for tx in rzp_txs if tx.settlement_id}

        j_rows = [
            r for r in gt
            if r["expected_relationship"] in ("ambiguous_1", "ambiguous_2")
        ]
        assert len(j_rows) >= 2, "Ground truth must contain Case J rows"

        for row in j_rows:
            sid = row["razorpay_record_id"]
            tx = rzp_by_sid.get(sid)
            assert tx is not None, f"Case J settlement {sid} not found in canonical dataset"

            dec = dec_by_src.get(tx.record_id)
            assert dec is not None, f"No decision for Case J record {tx.record_id}"
            assert dec.decision == "ambiguous", (
                f"Case J record {tx.record_id} (settlement {sid}) was NOT ambiguous! "
                f"Got decision={dec.decision}, method={dec.method}. "
                f"This may indicate the generated data does not produce genuine ambiguity."
            )

    def test_case_j_reaches_arbitration(self):
        """When LLM arbitration runs, Case J records must pass through the provider."""
        rzp_txs, bank_txs = _load_dataset()

        provider = MockArbitrationProvider(override_response={
            "decision": "ambiguous",
            "candidate_record_id": None,
            "confidence": 0.35,
            "reason": "Genuinely indistinguishable candidates.",
            "evidence": {},
        })
        arb = LLMArbitrationService(provider)
        result = reconcile(rzp_txs, bank_txs, arb)

        gt = _load_ground_truth()
        rzp_by_sid = {tx.settlement_id: tx for tx in rzp_txs if tx.settlement_id}
        j_sids = [
            r["razorpay_record_id"]
            for r in gt
            if r["expected_relationship"] in ("ambiguous_1", "ambiguous_2")
        ]

        dec_by_src = {d.source_record_id: d for d in result.decisions}
        for sid in j_sids:
            tx = rzp_by_sid.get(sid)
            if tx is None:
                continue
            dec = dec_by_src.get(tx.record_id)
            assert dec is not None
            assert dec.decision == "ambiguous"
            # Should have been processed by arbitration
            assert dec.method == "llm_arbitration", (
                f"Case J record {tx.record_id} did not reach LLM arbitration"
            )

        # Provider invocation count should include all ambiguous records
        assert provider.call_count >= len(j_sids), (
            f"Provider was called {provider.call_count} times but "
            f"expected at least {len(j_sids)} (Case J count)"
        )
