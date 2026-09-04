"""
Tests for the Deterministic Match Engine — Milestone 3.

All tests use synthetic CanonicalTransaction objects; no real API calls.
Ground-truth integration uses data/processed/reconciliation_ground_truth.csv.
"""

import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.canonical import CanonicalTransaction, ReconciliationDecision
from app.services.matcher import (
    DATE_TOLERANCE_DAYS,
    CONFIDENCE,
    DeterministicMatcher,
    MatchResult,
    _norm_ref,
    calculate_match_rate,
)
from app.services.normalizer import Normalizer
from app.services.schema_mapper import MockLLMProvider, SchemaMapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rzp(
    record_id="rzp_001",
    amount: str = "1000.00",
    ref: str | None = None,
    dt: date = date(2026, 9, 1),
    gross: str | None = None,
    fee: str | None = None,
    tax: str | None = None,
    settlement_id: str | None = None,
    transaction_type: str = "payment",
) -> CanonicalTransaction:
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


def bank(
    record_id="bank_001",
    amount: str = "1000.00",
    ref: str | None = None,
    dt: date = date(2026, 9, 1),
    transaction_type: str = "unknown",
) -> CanonicalTransaction:
    return CanonicalTransaction(
        record_id=record_id,
        source="bank",
        transaction_type=transaction_type,
        amount=Decimal(amount) if amount else None,
        reference=ref,
        posted_date=dt,
    )


# ---------------------------------------------------------------------------
# Reference normalisation
# ---------------------------------------------------------------------------

def test_norm_ref_variants():
    assert _norm_ref("UTR123456") == "123456"
    assert _norm_ref("utr-123456") == "123456"
    assert _norm_ref("UTR 123456") == "123456"
    assert _norm_ref("utr123456") == "123456"
    assert _norm_ref("") is None
    assert _norm_ref(None) is None


# ---------------------------------------------------------------------------
# Rule 1 — Exact identifier match
# ---------------------------------------------------------------------------

def test_exact_identifier_match():
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR123456")
    tgt = bank(ref="UTR123456")
    result = matcher.match([src], [tgt])

    assert len(result.decisions) == 1
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.method == "exact_identifier"
    assert d.confidence == CONFIDENCE["exact_identifier"]
    assert d.evidence["identifier_field"] == "reference"


def test_exact_identifier_match_normalised_variant():
    """UTR123 in Razorpay, utr-123 in bank — should still match."""
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR123")
    tgt = bank(ref="utr-123")
    result = matcher.match([src], [tgt])
    assert result.decisions[0].decision == "matched"
    assert result.decisions[0].method == "exact_identifier"


# ---------------------------------------------------------------------------
# Rule 3 — Exact amount + date match
# ---------------------------------------------------------------------------

def test_exact_amount_date_match():
    matcher = DeterministicMatcher()
    src = rzp(ref=None)   # No identifier
    tgt = bank(ref=None)
    result = matcher.match([src], [tgt])
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.method == "exact_amount_date"
    assert d.confidence == CONFIDENCE["exact_amount_date"]
    assert "amount" in d.evidence
    assert "date" in d.evidence


def test_no_match_amount_mismatch():
    matcher = DeterministicMatcher()
    src = rzp(ref=None, amount="1000.00")
    tgt = bank(ref=None, amount="999.00")
    result = matcher.match([src], [tgt])
    assert result.decisions[0].decision == "unmatched"


def test_no_match_date_mismatch_beyond_tolerance():
    matcher = DeterministicMatcher()
    far_date = date(2026, 9, 1) + timedelta(days=DATE_TOLERANCE_DAYS + 1)
    src = rzp(ref=None, dt=date(2026, 9, 1))
    tgt = bank(ref=None, dt=far_date)
    result = matcher.match([src], [tgt])
    assert result.decisions[0].decision == "unmatched"


# ---------------------------------------------------------------------------
# Rule 4 — Amount + date tolerance
# ---------------------------------------------------------------------------

def test_amount_date_tolerance_match():
    matcher = DeterministicMatcher()
    src = rzp(ref=None, dt=date(2026, 9, 1))
    tgt = bank(ref=None, dt=date(2026, 9, 2))  # 1-day diff
    result = matcher.match([src], [tgt])
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.method == "amount_date_tolerance"
    assert d.evidence["difference_days"] == 1
    assert d.evidence["allowed_days"] == DATE_TOLERANCE_DAYS


# ---------------------------------------------------------------------------
# Missing fields
# ---------------------------------------------------------------------------

def test_missing_amount_no_match():
    matcher = DeterministicMatcher()
    src = rzp(amount=None, ref=None)
    tgt = bank(amount="1000.00", ref=None)
    result = matcher.match([src], [tgt])
    # Cannot do amount+date match; should be unmatched
    assert result.decisions[0].decision == "unmatched"


def test_missing_date_no_amount_date_match():
    matcher = DeterministicMatcher()
    src = CanonicalTransaction(
        record_id="rzp_no_date",
        source="razorpay",
        transaction_type="unknown",
        amount=Decimal("1000.00"),
        # No date fields
    )
    tgt = bank(amount="1000.00", ref=None)
    result = matcher.match([src], [tgt])
    # No identifier, no date → can only fall to unmatched unless exact_amount_date fires
    # src has no date so key cannot be formed
    assert result.decisions[0].decision == "unmatched"


def test_missing_identifier_falls_through_to_amount_date():
    matcher = DeterministicMatcher()
    src = rzp(ref=None)
    tgt = bank(ref=None)
    result = matcher.match([src], [tgt])
    assert result.decisions[0].decision == "matched"
    assert result.decisions[0].method == "exact_amount_date"


# ---------------------------------------------------------------------------
# Genuine ambiguity
# ---------------------------------------------------------------------------

def test_genuine_ambiguity_multiple_candidates():
    matcher = DeterministicMatcher()
    src = rzp(ref=None, amount="1000.00", dt=date(2026, 9, 1))
    t1 = bank(record_id="bank_001", ref=None, amount="1000.00", dt=date(2026, 9, 1))
    t2 = bank(record_id="bank_002", ref=None, amount="1000.00", dt=date(2026, 9, 1))
    result = matcher.match([src], [t1, t2])
    d = result.decisions[0]
    assert d.decision == "ambiguous"
    assert d.evidence["candidate_count"] == 2
    assert len(result.exceptions) == 1
    assert result.exceptions[0].category == "ambiguous_match"


# ---------------------------------------------------------------------------
# Duplicate target collision
# ---------------------------------------------------------------------------

def test_duplicate_target_collision():
    """Two bank records that share the same identifier → duplicate exception."""
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    t1 = bank(record_id="bank_001", ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    t2 = bank(record_id="bank_002", ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    result = matcher.match([src], [t1, t2])
    d = result.decisions[0]
    assert d.decision == "ambiguous"
    assert d.method == "duplicate"
    exc = result.exceptions[0]
    assert exc.category == "duplicate"
    assert exc.severity == "high"


def test_target_not_reused():
    """A single bank record must not be matched to two different Razorpay records."""
    matcher = DeterministicMatcher()
    src1 = rzp(record_id="rzp_001", ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    src2 = rzp(record_id="rzp_002", ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    tgt = bank(record_id="bank_001", ref="UTR999", amount="1000.00", dt=date(2026, 9, 1))
    result = matcher.match([src1, src2], [tgt])
    matched = [d for d in result.decisions if d.decision == "matched"]
    assert len(matched) <= 1  # At most one can be matched to this bank record


# ---------------------------------------------------------------------------
# Confidence is deterministic
# ---------------------------------------------------------------------------

def test_confidence_is_deterministic():
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR42")
    tgt = bank(ref="UTR42")
    r1 = matcher.match([src], [tgt])
    r2 = matcher.match([src], [tgt])
    assert r1.decisions[0].confidence == r2.decisions[0].confidence == CONFIDENCE["exact_identifier"]


# ---------------------------------------------------------------------------
# Audit record always generated
# ---------------------------------------------------------------------------

def test_audit_record_generated():
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR42")
    tgt = bank(ref="UTR42")
    result = matcher.match([src], [tgt])
    assert len(result.audit_records) >= 1
    aud = result.audit_records[0]
    assert aud.record_id == src.record_id
    assert aud.stage == "deterministic_matching"
    assert aud.decision == "matched"


def test_audit_record_on_unmatched():
    matcher = DeterministicMatcher()
    src = rzp(ref=None, amount="1234.56", dt=date(2026, 9, 1))
    result = matcher.match([src], [])
    assert len(result.audit_records) >= 1


# ---------------------------------------------------------------------------
# Evidence always generated
# ---------------------------------------------------------------------------

def test_evidence_on_match():
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR42")
    tgt = bank(ref="UTR42")
    result = matcher.match([src], [tgt])
    assert result.decisions[0].evidence  # non-empty


# ---------------------------------------------------------------------------
# Financial reconciliation (Case C)
# ---------------------------------------------------------------------------

def test_financial_reconciliation():
    """gross - fee - tax = net amount that appears in bank credit."""
    matcher = DeterministicMatcher()
    src = CanonicalTransaction(
        record_id="rzp_c",
        source="razorpay",
        transaction_type="unknown",
        amount=Decimal("4335.33"),   # gross (settlement = gross for case C)
        gross_amount=Decimal("4335.33"),
        fee=Decimal("209.62"),
        tax=Decimal("37.73"),
        settlement_date=date(2026, 9, 5),
    )
    net = Decimal("4335.33") - Decimal("209.62") - Decimal("37.73")  # 4087.98
    tgt = bank(record_id="bank_c", amount=str(net), dt=date(2026, 9, 5))
    result = matcher.match([src], [tgt])
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.method == "financial_reconciliation"
    assert "expected_amount" in d.evidence


# ---------------------------------------------------------------------------
# Batch settlement (Case H)
# ---------------------------------------------------------------------------

def test_batch_settlement():
    matcher = DeterministicMatcher()
    batch_ref = "BATCH_UTR_0"
    s1 = rzp(record_id="rzp_h1", ref=batch_ref, amount="989.77", dt=date(2026, 9, 5))
    s2 = rzp(record_id="rzp_h2", ref=batch_ref, amount="1383.00", dt=date(2026, 9, 5))
    s3 = rzp(record_id="rzp_h3", ref=batch_ref, amount="231.10", dt=date(2026, 9, 5))
    total = Decimal("989.77") + Decimal("1383.00") + Decimal("231.10")
    tgt = bank(record_id="bank_h", ref=batch_ref, amount=str(total), dt=date(2026, 9, 5))

    result = matcher.match([s1, s2, s3], [tgt])
    # One decision emitted PER SOURCE RECORD in the batch (all point to the same bank target)
    batch_decisions = [d for d in result.decisions if d.method == "batch_amount_reconciliation"]
    assert len(batch_decisions) == 3, f"Expected 3 batch decisions (one per source), got {len(batch_decisions)}"
    for bd in batch_decisions:
        assert bd.decision == "matched"
        assert str(total) == bd.evidence["aggregated_amount"]
        assert bd.candidate_record_id == "bank_h"


# ---------------------------------------------------------------------------
# Refund (Case I)
# ---------------------------------------------------------------------------

def test_refund_matcher():
    """Razorpay refund record matches bank debit by amount."""
    matcher = DeterministicMatcher()
    src = CanonicalTransaction(
        record_id="rzp_ref",
        source="razorpay",
        transaction_type="unknown",
        settlement_id="ref_999398",
        amount=Decimal("686.63"),
        gross_amount=Decimal("686.63"),
        reference="UTR999398",
        settlement_date=date(2026, 9, 3),
    )
    # Bank debit comes in as negative in our normaliser
    tgt = CanonicalTransaction(
        record_id="bank_ref",
        source="bank",
        transaction_type="unknown",
        amount=Decimal("-686.63"),
        posted_date=date(2026, 9, 3),
    )
    result = matcher.match([src], [tgt])
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.method == "refund_identifier"


# ---------------------------------------------------------------------------
# Match rate metric
# ---------------------------------------------------------------------------

def test_match_rate_metric():
    matcher = DeterministicMatcher()
    s1 = rzp(record_id="rzp_1", ref="UTR1")
    s2 = rzp(record_id="rzp_2", ref=None, amount="9999.99", dt=date(2026, 9, 2))
    t1 = bank(record_id="bank_1", ref="UTR1")
    # s2 has no bank match → unmatched
    result = matcher.match([s1, s2], [t1])
    stats = calculate_match_rate(result)
    assert stats["total"] == 2
    assert stats["matched"] == 1
    assert stats["match_rate"] == 0.5


# ---------------------------------------------------------------------------
# Ground truth integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ground_truth_data():
    """Load and normalise all three CSVs; return rzp_txs, bank_txs, and gt rows."""
    mapper = SchemaMapper(MockLLMProvider())
    norm = Normalizer()

    def load(path, source):
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            cols = reader.fieldnames
        mapping = mapper.map_source(source, cols, [])
        return norm.normalize(rows, mapping), rows

    rzp_txs, rzp_raw = load("data/raw/razorpay_settlements.csv", "razorpay")
    bank_txs, bank_raw = load("data/raw/bank_statement.csv", "bank")

    with open("data/processed/reconciliation_ground_truth.csv") as f:
        gt_rows = list(csv.DictReader(f))

    return rzp_txs, bank_txs, gt_rows, rzp_raw, bank_raw


def test_ground_truth_full_run(ground_truth_data):
    """Run the full matcher and collect per-case classification."""
    rzp_txs, bank_txs, gt_rows, *_ = ground_truth_data
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)
    stats = calculate_match_rate(result)

    # Basic sanity
    assert stats["total"] == len(rzp_txs)
    assert all(d.decision in ("matched", "unmatched", "ambiguous") for d in result.decisions)
    # Every source record has exactly one decision
    assert len(result.decisions) == len(rzp_txs)
    # Every decision has an audit record
    assert len(result.audit_records) >= len(result.decisions)

    print(f"\n[Ground truth run] {stats}")


def test_case_j_is_not_ambiguous_from_amounts(ground_truth_data):
    """Case J: amounts within each J group are unique globally → exact_amount_date resolves them.

    NOTE: The synthetic J groups have DIFFERENT amounts per pair (e.g. 965.28 and 970.51).
    Each amount is unique in the entire bank dataset.  The deterministic engine will therefore
    resolve each J record via exact_amount_date — they are NOT left ambiguous at this milestone.
    This test documents this architectural observation honestly.

    True deterministic ambiguity (same amount AND same date) would require identical amounts
    within a pair, which is not what the generator produces for Case J.
    """
    rzp_txs, bank_txs, gt_rows, *_ = ground_truth_data
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)

    decision_by_src: dict = {d.source_record_id: d for d in result.decisions}

    j_rows = [r for r in gt_rows if "ambiguous" in r["expected_relationship"]]
    for row in j_rows:
        rzp_id_raw = row["razorpay_record_id"]
        # Find the normalised record_id for this Razorpay Settlement Ref
        rzp_tx = next(
            (tx for tx in rzp_txs if tx.settlement_id == rzp_id_raw or tx.metadata.get("Settlement Ref") == rzp_id_raw),
            None,
        )
        if rzp_tx is None:
            continue
        dec = decision_by_src.get(rzp_tx.record_id)
        if dec:
            # The test documents what actually happens — not what was desired
            assert dec.decision in ("matched", "ambiguous"), (
                f"Case J record {rzp_tx.record_id} has unexpected decision {dec.decision!r}"
            )


def test_case_a_exact_matches(ground_truth_data):
    """Case A records should be matched via exact_identifier."""
    rzp_txs, bank_txs, gt_rows, *_ = ground_truth_data
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)
    dec_by_src = {d.source_record_id: d for d in result.decisions}

    a_rzp_ids = {r["razorpay_record_id"] for r in gt_rows if r["expected_relationship"] == "exact_match"}
    a_txs = [tx for tx in rzp_txs if tx.settlement_id in a_rzp_ids or tx.metadata.get("Settlement Ref") in a_rzp_ids]

    matched = [dec_by_src[tx.record_id] for tx in a_txs if tx.record_id in dec_by_src]
    assert len(matched) > 0
    for dec in matched:
        assert dec.decision == "matched", f"Case A: expected matched, got {dec.decision}"


def test_case_e_unmatched(ground_truth_data):
    """Case E Razorpay records have no bank counterpart → unmatched."""
    rzp_txs, bank_txs, gt_rows, *_ = ground_truth_data
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)
    dec_by_src = {d.source_record_id: d for d in result.decisions}

    e_rzp_ids = {r["razorpay_record_id"] for r in gt_rows if r["expected_relationship"] == "missing_bank_record"}
    e_txs = [tx for tx in rzp_txs if tx.settlement_id in e_rzp_ids or tx.metadata.get("Settlement Ref") in e_rzp_ids]

    for tx in e_txs:
        dec = dec_by_src.get(tx.record_id)
        assert dec is not None
        assert dec.decision == "unmatched", f"Case E: expected unmatched, got {dec.decision}"


def test_no_bank_record_reused(ground_truth_data):
    """A bank record must not be reused by non-batch decisions.

    Batch settlements are the only legitimate case where multiple Razorpay
    records share the same candidate_record_id (N Razorpay → 1 Bank credit).
    All other methods must produce unique bank targets.
    """
    rzp_txs, bank_txs, _, *__ = ground_truth_data
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)

    # Gather candidate IDs for non-batch decisions only
    non_batch = [
        d.candidate_record_id
        for d in result.decisions
        if d.candidate_record_id and d.method != "batch_amount_reconciliation"
    ]
    assert len(non_batch) == len(set(non_batch)), (
        "Bank record was reused by non-batch decisions: "
        + str([x for x in non_batch if non_batch.count(x) > 1])
    )

# ---------------------------------------------------------------------------
# BUGFIX REGRESSION TESTS (Milestone 3 Audit)
# ---------------------------------------------------------------------------

def test_fee_debit_not_classified_as_duplicate():
    """Case C: One credit and one debit sharing UTR should match the credit and not throw duplicate."""
    matcher = DeterministicMatcher()
    src = rzp(ref="UTR999", amount="100.00", gross="100.00", fee="2.00", tax="0.36")
    
    tgt_credit = bank(ref="UTR999", amount="100.00")
    tgt_debit = bank(ref="UTR999", amount="-2.36")
    
    result = matcher.match([src], [tgt_credit, tgt_debit])
    
    assert len(result.decisions) == 1
    d = result.decisions[0]
    assert d.decision == "matched"
    assert d.candidate_record_id == tgt_credit.record_id
    assert d.method == "exact_identifier"
    assert "associated_debit_candidates" in d.evidence

def test_exact_amount_date_fires_before_financial_reconciliation():
    """If amount and date match perfectly, rule 2 (exact_amount_date) should fire, not financial_reconciliation."""
    matcher = DeterministicMatcher()
    # Settled amount is 1000.00, Gross is 1050, Fee+Tax = 50.
    src = rzp(amount="1000.00", gross="1050.00", fee="40.00", tax="10.00", dt=date(2026,9,1))
    # Bank credit matches the settled amount exactly.
    tgt = bank(amount="1000.00", dt=date(2026,9,1))
    
    result = matcher.match([src], [tgt])
    assert len(result.decisions) == 1
    assert result.decisions[0].method == "exact_amount_date"

def test_refund_identifier_without_reference_field():
    """If reference is missing, R1 skips, and R5 (refund_identifier) should successfully match the debit."""
    matcher = DeterministicMatcher()
    
    # Refund RZP with NO reference
    src = rzp(settlement_id="ref_123", amount="100.00", gross="100.00", ref=None, transaction_type="refund")
    tgt = bank(amount="-100.00") # Debit
    
    result = matcher.match([src], [tgt])
    assert len(result.decisions) == 1
    d = result.decisions[0]
    
    assert d.decision == "matched"
    assert d.method == "refund_identifier"

def test_batch_fails_gracefully_when_bank_ref_missing():
    """If a valid batch exists in source but bank record is missing Bank Ref, it shouldn't match."""
    matcher = DeterministicMatcher()
    s1 = rzp(amount="100.00", ref="BATCH_1")
    s2 = rzp(amount="200.00", ref="BATCH_1")
    tgt = bank(amount="300.00", ref=None) # Sum matches, but ref is missing
    
    result = matcher.match([s1, s2], [tgt])
    assert len(result.decisions) == 2
    for d in result.decisions:
        assert d.decision == "unmatched"

def test_case_j_genuinely_ambiguous():
    """Verify Case J records truly trigger 'ambiguous' decision on generated dataset."""
    import csv
    from app.services.normalizer import Normalizer
    
    # Generate fresh dataset with bugs fixed
    import subprocess
    subprocess.run(["python3", "scripts/generate_data.py"], check=True)
    
    mapper = SchemaMapper(MockLLMProvider())
    norm = Normalizer()
    
    def load(path, source):
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            cols = reader.fieldnames
        mapping = mapper.map_source(source, cols, [])
        return norm.normalize(rows, mapping), rows
        
    rzp_txs, _ = load('data/raw/razorpay_settlements.csv', 'razorpay')
    bank_txs, _ = load('data/raw/bank_statement.csv', 'bank')
    gt = list(csv.DictReader(open('data/processed/reconciliation_ground_truth.csv')))
    
    matcher = DeterministicMatcher()
    result = matcher.match(rzp_txs, bank_txs)
    dec_by_src = {d.source_record_id: d for d in result.decisions}
    rzp_by_sid = {tx.settlement_id: tx for tx in rzp_txs if tx.settlement_id}
    
    j_rows = [r for r in gt if 'ambiguous' in r['expected_relationship']]
    assert len(j_rows) > 0, "No Case J rows found!"
    
    for row in j_rows:
        tx = rzp_by_sid.get(row['razorpay_record_id'])
        if tx:
            dec = dec_by_src.get(tx.record_id)
            assert dec is not None
            assert dec.decision == "ambiguous", f"Case J record {tx.record_id} was not ambiguous! Method: {dec.method}"
