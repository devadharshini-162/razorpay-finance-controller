import pytest
from decimal import Decimal
from datetime import date

from app.models.canonical import CanonicalTransaction, ReconciliationDecision
from app.services.matcher import MatchResult
from app.services.arbitrator import LLMArbitrationService
from app.services.arbitration_provider import MockArbitrationProvider

def make_tx(record_id, amount, ref=None, source="razorpay"):
    return CanonicalTransaction(
        record_id=record_id,
        source=source,
        transaction_type="payment",
        amount=Decimal(amount) if amount else None,
        reference=ref,
        settlement_date=date(2026, 9, 1)
    )

def test_skips_matched_and_unmatched():
    """Provider should NOT be called for matched or unmatched decisions."""
    provider = MockArbitrationProvider()
    service = LLMArbitrationService(provider)
    
    res = MatchResult(
        decisions=[
            ReconciliationDecision(
                decision_id="d1", source_record_id="s1", candidate_record_id="c1",
                decision="matched", method="exact", confidence=1.0
            ),
            ReconciliationDecision(
                decision_id="d2", source_record_id="s2", candidate_record_id=None,
                decision="unmatched", method="unmatched", confidence=0.1
            )
        ]
    )
    
    src = [make_tx("s1", "10"), make_tx("s2", "20")]
    tgt = [make_tx("c1", "10", source="bank")]
    
    service.process_match_result(res, src, tgt)
    assert provider.call_count == 0

def test_ambiguous_record_invokes_provider():
    """Provider should be called exactly once for an ambiguous decision."""
    provider = MockArbitrationProvider(override_response={
        "decision": "matched",
        "candidate_record_id": "c1",
        "confidence": 0.9,
        "reason": "Test",
        "evidence": {}
    })
    service = LLMArbitrationService(provider)
    
    res = MatchResult(
        decisions=[
            ReconciliationDecision(
                decision_id="d1", source_record_id="s1", candidate_record_id=None,
                decision="ambiguous", method="ambiguous", confidence=0.4,
                evidence={"candidate_record_ids": ["c1", "c2"]} # Candidates
            )
        ]
    )
    
    src = [make_tx("s1", "10")]
    tgt = [make_tx("c1", "10", source="bank"), make_tx("c2", "10", source="bank")]
    
    updated_res = service.process_match_result(res, src, tgt)
    assert provider.call_count == 1
    
    # Should be upgraded to matched
    d = updated_res.decisions[0]
    assert d.decision == "matched"
    assert d.candidate_record_id == "c1"
    assert d.method == "llm_arbitration"
    assert "llm_evidence" in d.evidence

def test_reject_hallucinated_candidate():
    """Service must reject a candidate_record_id not in the original candidate pool."""
    provider = MockArbitrationProvider(override_response={
        "decision": "matched",
        "candidate_record_id": "HALLUCINATED_ID",
        "confidence": 0.9,
        "reason": "I invented this.",
        "evidence": {}
    })
    service = LLMArbitrationService(provider)
    
    res = MatchResult(
        decisions=[
            ReconciliationDecision(
                decision_id="d1", source_record_id="s1", candidate_record_id=None,
                decision="ambiguous", method="ambiguous", confidence=0.4,
                evidence={"candidate_record_ids": ["c1", "c2"]} 
            )
        ]
    )
    
    src = [make_tx("s1", "10")]
    tgt = [make_tx("c1", "10", source="bank"), make_tx("c2", "10", source="bank")]
    
    updated_res = service.process_match_result(res, src, tgt)
    assert provider.call_count == 1
    
    # Must remain ambiguous!
    d = updated_res.decisions[0]
    assert d.decision == "ambiguous"
    assert d.candidate_record_id is None
    assert d.method == "ambiguous"

def test_reject_malformed_response():
    """Service must handle malformed response (e.g. wrong type or missing fields) safely."""
    provider = MockArbitrationProvider(override_response={
        "decision": "UNKNOWN_GARBAGE", # Invalid literal
        "confidence": 999.0 # Out of bounds
    })
    service = LLMArbitrationService(provider)
    
    res = MatchResult(
        decisions=[
            ReconciliationDecision(
                decision_id="d1", source_record_id="s1", candidate_record_id=None,
                decision="ambiguous", method="ambiguous", confidence=0.4,
                evidence={"candidate_record_ids": ["c1", "c2"]} 
            )
        ]
    )
    
    src = [make_tx("s1", "10")]
    tgt = [make_tx("c1", "10", source="bank"), make_tx("c2", "10", source="bank")]
    
    updated_res = service.process_match_result(res, src, tgt)
    assert provider.call_count == 1
    
    d = updated_res.decisions[0]
    assert d.decision == "ambiguous"
    assert d.method == "ambiguous"

def test_genuine_ambiguity_remains_ambiguous():
    """Provider can explicitly return ambiguous if it cannot decide."""
    provider = MockArbitrationProvider(override_response={
        "decision": "ambiguous",
        "candidate_record_id": None,
        "confidence": 0.4,
        "reason": "Still ambiguous.",
        "evidence": {}
    })
    service = LLMArbitrationService(provider)
    
    res = MatchResult(
        decisions=[
            ReconciliationDecision(
                decision_id="d1", source_record_id="s1", candidate_record_id=None,
                decision="ambiguous", method="duplicate", confidence=0.4,
                evidence={"candidate_record_ids": ["c1", "c2"]} 
            )
        ]
    )
    
    src = [make_tx("s1", "10")]
    tgt = [make_tx("c1", "10", source="bank"), make_tx("c2", "10", source="bank")]
    
    updated_res = service.process_match_result(res, src, tgt)
    
    # State should update its method to show it went through llm
    d = updated_res.decisions[0]
    assert d.decision == "ambiguous"
    assert d.method == "llm_arbitration"
    assert "llm_evidence" in d.evidence
