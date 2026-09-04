import pytest
from decimal import Decimal
from datetime import date
from pydantic import ValidationError

from app.models.canonical import (
    CanonicalTransaction,
    ReconciliationDecision,
    ExceptionRecord,
    AuditRecord
)

# --- CanonicalTransaction Tests ---

def test_canonical_transaction_minimal():
    tx = CanonicalTransaction(
        record_id="rec_1",
        source="razorpay",
        transaction_type="payment"
    )
    assert tx.record_id == "rec_1"
    assert tx.source == "razorpay"
    assert tx.transaction_type == "payment"
    assert tx.amount is None
    assert tx.metadata == {}

def test_canonical_transaction_full():
    tx = CanonicalTransaction(
        record_id="rec_2",
        source="bank",
        transaction_type="settlement",
        transaction_id="tx_123",
        order_id="order_456",
        settlement_id="set_789",
        reference="ref_xyz",
        amount=Decimal("100.50"),
        gross_amount=Decimal("102.50"),
        fee=Decimal("1.50"),
        tax=Decimal("0.50"),
        adjustment=Decimal("0"),
        refund_amount=Decimal("0"),
        currency="INR",
        transaction_date=date(2023, 10, 1),
        settlement_date=date(2023, 10, 2),
        posted_date=date(2023, 10, 3),
        counterparty="Razorpay",
        description="Settlement for Oct 1",
        metadata={"extra_field": "value"}
    )
    assert tx.amount == Decimal("100.50")
    assert tx.transaction_date == date(2023, 10, 1)

def test_canonical_transaction_decimal():
    tx = CanonicalTransaction(
        record_id="rec_3",
        source="bank",
        transaction_type="payment",
        amount=Decimal("9787.60")
    )
    assert tx.amount == Decimal("9787.60")

def test_canonical_transaction_metadata_isolated():
    tx1 = CanonicalTransaction(record_id="rec_4", source="bank", transaction_type="payment")
    tx2 = CanonicalTransaction(record_id="rec_5", source="bank", transaction_type="payment")
    
    tx1.metadata["test"] = "value"
    
    assert "test" in tx1.metadata
    assert "test" not in tx2.metadata

def test_canonical_transaction_forbids_extra():
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            record_id="rec_6",
            source="bank",
            transaction_type="payment",
            unknown_top_level="reject_me"
        )

def test_canonical_transaction_required_fields():
    with pytest.raises(ValidationError):
        CanonicalTransaction(source="bank") # Missing record_id and tx type
    with pytest.raises(ValidationError):
        CanonicalTransaction(record_id="rec_7") # Missing source and tx type

def test_canonical_transaction_invalid_type():
    with pytest.raises(ValidationError):
        CanonicalTransaction(
            record_id="rec_8",
            source="bank",
            transaction_type="invalid_type"
        )

# --- ReconciliationDecision Tests ---

def test_reconciliation_decision_valid():
    rd = ReconciliationDecision(
        decision_id="dec_1",
        source_record_id="rec_1",
        decision="matched",
        method="deterministic",
        confidence=1.0,
        candidate_record_id="cand_1",
        evidence={"score": 100}
    )
    assert rd.decision == "matched"
    assert rd.confidence == 1.0

def test_reconciliation_decision_unmatched():
    rd = ReconciliationDecision(
        decision_id="dec_2",
        source_record_id="rec_2",
        decision="unmatched",
        method="fuzzy",
        confidence=0.0
    )
    assert rd.decision == "unmatched"
    assert rd.evidence == {}
    assert rd.candidate_record_id is None

def test_reconciliation_decision_ambiguous():
    rd = ReconciliationDecision(
        decision_id="dec_3",
        source_record_id="rec_3",
        decision="ambiguous",
        method="llm",
        confidence=0.5,
        candidate_record_id="cand_2"
    )
    assert rd.decision == "ambiguous"
    assert rd.confidence == 0.5

def test_reconciliation_decision_confidence_bounds():
    with pytest.raises(ValidationError):
        ReconciliationDecision(
            decision_id="d1", source_record_id="s1", decision="matched", method="test", confidence=-0.1
        )
    with pytest.raises(ValidationError):
        ReconciliationDecision(
            decision_id="d2", source_record_id="s2", decision="matched", method="test", confidence=1.1
        )
        
def test_reconciliation_decision_confidence_bounds_accept():
    d1 = ReconciliationDecision(
        decision_id="d1", source_record_id="s1", decision="matched", method="test", confidence=0
    )
    d2 = ReconciliationDecision(
        decision_id="d2", source_record_id="s2", decision="matched", method="test", confidence=1
    )
    assert d1.confidence == 0.0
    assert d2.confidence == 1.0

def test_reconciliation_decision_forbids_extra():
    with pytest.raises(ValidationError):
        ReconciliationDecision(
            decision_id="d3", source_record_id="s3", decision="matched", method="test", confidence=1.0, extra="invalid"
        )

# --- ExceptionRecord Tests ---

def test_exception_record_valid():
    er = ExceptionRecord(
        exception_id="exc_1",
        record_id="rec_1",
        category="amount_difference",
        severity="high",
        reason="Amounts differ by 10.00",
        confidence=0.9
    )
    assert er.category == "amount_difference"
    assert er.confidence == 0.9

def test_exception_record_all_categories():
    categories = [
        "missing_record", "amount_difference", "date_mismatch",
        "duplicate", "ambiguous_match", "batch_settlement",
        "refund_mismatch", "unknown"
    ]
    for i, cat in enumerate(categories):
        er = ExceptionRecord(
             exception_id=f"exc_{i}", record_id="r", category=cat, severity="low", reason="test", confidence=0.5
        )
        assert er.category == cat

def test_exception_record_severity_validation():
    with pytest.raises(ValidationError):
         ExceptionRecord(
             exception_id="e1", record_id="r1", category="unknown", severity="critical", reason="bad", confidence=0.5
         )

def test_exception_record_confidence_bounds():
    with pytest.raises(ValidationError):
        ExceptionRecord(
             exception_id="e1", record_id="r1", category="unknown", severity="low", reason="bad", confidence=1.5
        )

def test_exception_record_evidence_works():
    er = ExceptionRecord(
             exception_id="e1", record_id="r1", category="unknown", severity="low", reason="bad", confidence=0.5,
             evidence={"diff": 5}
    )
    assert er.evidence["diff"] == 5

def test_exception_record_forbids_extra():
    with pytest.raises(ValidationError):
        ExceptionRecord(
             exception_id="e1", record_id="r1", category="unknown", severity="low", reason="bad", confidence=0.5,
             extra_field="error"
        )


# --- AuditRecord Tests ---

def test_audit_record_valid():
    ar = AuditRecord(
        audit_id="a_1",
        record_id="r_1",
        stage="matching",
        action="compared_ids",
        method="deterministic",
        decision="exact_match"
    )
    assert ar.stage == "matching"

def test_audit_record_evidence_works():
    ar = AuditRecord(
        audit_id="a_1",
        record_id="r_1",
        stage="matching",
        action="compared_ids",
        method="deterministic",
        decision="exact_match",
        evidence={"val": 42}
    )
    assert ar.evidence["val"] == 42
    
def test_audit_record_invalid_extra():
    with pytest.raises(ValidationError):
        AuditRecord(
            audit_id="a_1", record_id="r_1", stage="matching", action="some", method="some", decision="matched", invalid="field"
        )

def test_audit_record_mutable_defaults():
    ar1 = AuditRecord(
        audit_id="a_1", record_id="r_1", stage="stage", action="act", method="met", decision="dec"
    )
    ar2 = AuditRecord(
        audit_id="a_2", record_id="r_2", stage="stage", action="act", method="met", decision="dec"
    )
    ar1.evidence["foo"] = "bar"
    assert "foo" not in ar2.evidence
