import pytest
from datetime import date
from decimal import Decimal
import csv
from app.services.normalizer import Normalizer
from app.models.mapping import MappingResult
from app.services.schema_mapper import SchemaMapper, MockLLMProvider

def test_normalizer_unique_deterministic_record_ids():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={}, confidence=1.0)
    raw = [{"a": 1}, {"a": 2}]
    txs = norm.normalize(raw, mapping)
    assert txs[0].record_id == "test_src_0001"
    assert txs[1].record_id == "test_src_0002"

def test_normalizer_date_conversion():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"dt": "transaction_date"}, confidence=1.0)
    raw = [{"dt": "2026-09-01"}, {"dt": "01/09/2026"}, {"dt": "01-09-2026"}, {"dt": "Sep 01 2026"}]
    txs = norm.normalize(raw, mapping)
    for tx in txs:
        assert tx.transaction_date == date(2026, 9, 1)

def test_normalizer_decimal_amounts():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "10000"}, {"amt": "10000.00"}, {"amt": "₹10,000.00"}, {"amt": "10,000.00"}]
    txs = norm.normalize(raw, mapping)
    for tx in txs:
        assert tx.amount == Decimal("10000.00")

def test_normalizer_handles_blank_values():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"amt": "amount", "empty": "description"}, confidence=1.0)
    raw = [{"amt": "", "empty": "   "}, {"amt": None, "empty": None}]
    txs = norm.normalize(raw, mapping)
    assert txs[0].amount is None
    assert txs[0].description is None
    assert txs[1].amount is None
    assert txs[1].description is None

def test_normalizer_preserves_unmapped_metadata():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "100", "Branch": "CHN001", "Running Balance": "125430.50"}]
    txs = norm.normalize(raw, mapping)
    assert txs[0].metadata["Branch"] == "CHN001"
    assert txs[0].metadata["Running Balance"] == "125430.50"

def test_normalizer_missing_concepts_remain_none():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "100"}]
    txs = norm.normalize(raw, mapping)
    assert txs[0].fee is None
    assert txs[0].tax is None
    assert txs[0].transaction_date is None

def test_normalizer_handles_invalid_monetary_amount():
    norm = Normalizer()
    mapping = MappingResult(source_name="test_src", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "not_an_amount"}]
    with pytest.raises(ValueError, match="Could not parse monetary amount"):
        norm.normalize(raw, mapping)

def test_normalizer_credit_debit_semantics():
    """Credit column → positive amount, Debit column → negative amount."""
    norm = Normalizer()
    mapping = MappingResult(
        source_name="bank",
        column_mapping={"Credit": "amount", "Debit": "amount"},
        confidence=1.0
    )
    # Row 0: credit only
    # Row 1: debit only
    # Row 2: both present (edge case — net result)
    raw = [
        {"Credit": "100.00", "Debit": ""},
        {"Credit": "", "Debit": "50.00"},
        {"Credit": "200.00", "Debit": "30.00"},
    ]
    txs = norm.normalize(raw, mapping)
    assert txs[0].amount == Decimal("100.00")    # credit → positive
    assert txs[1].amount == Decimal("-50.00")    # debit  → negative
    assert txs[2].amount == Decimal("170.00")    # net: 200 - 30

def test_normalizer_does_not_invent_values():
    norm = Normalizer()
    mapping = MappingResult(source_name="bank", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "100.00"}]
    txs = norm.normalize(raw, mapping)
    # Check that it did not invent a transaction_date, currency, or other fields
    assert txs[0].currency is None
    assert txs[0].transaction_date is None
    assert txs[0].reference is None
    assert txs[0].fee is None
    
def test_normalizer_transaction_type_is_strict():
    norm = Normalizer()
    mapping = MappingResult(source_name="bank", column_mapping={"amt": "amount"}, confidence=1.0)
    raw = [{"amt": "100.00", "desc": "RAZORPAY REFUND"}]
    txs = norm.normalize(raw, mapping)
    # It must NOT guess refund from narration now!
    assert txs[0].transaction_type == "unknown"

def test_integration_razorpay():
    with open("data/raw/razorpay_settlements.csv", "r") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
        columns = reader.fieldnames
        
    mapper = SchemaMapper(MockLLMProvider())
    mapping = mapper.map_source("razorpay", columns, [])
    
    norm = Normalizer()
    txs = norm.normalize(raw, mapping)
    
    assert len(txs) > 0
    for tx in txs:
        assert str(tx.source) == "razorpay"
        assert tx.transaction_type == "unknown"

def test_integration_bank():
    with open("data/raw/bank_statement.csv", "r") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
        columns = reader.fieldnames
        
    mapper = SchemaMapper(MockLLMProvider())
    mapping = mapper.map_source("bank", columns, [])
    
    norm = Normalizer()
    txs = norm.normalize(raw, mapping)
    assert len(txs) > 0
    for tx in txs:
        assert str(tx.source) == "bank"
        assert tx.transaction_type == "unknown"

def test_integration_bank_credit_debit_sign():
    """Bank rows with non-empty Debit must produce negative amounts."""
    with open("data/raw/bank_statement.csv", "r") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
        columns = reader.fieldnames

    mapper = SchemaMapper(MockLLMProvider())
    mapping = mapper.map_source("bank", columns, [])

    # Confirm both Credit and Debit are in the mapping
    assert "Credit" in mapping.column_mapping
    assert "Debit" in mapping.column_mapping
    assert mapping.column_mapping["Credit"] == "amount"
    assert mapping.column_mapping["Debit"] == "amount"

    norm = Normalizer()
    txs = norm.normalize(raw, mapping)

    debit_rows  = [r for r in raw if r.get("Debit")]
    credit_rows = [r for r in raw if r.get("Credit") and not r.get("Debit")]

    # Map record_id → tx for easy lookup
    tx_by_id = {tx.record_id: tx for tx in txs}
    rzp_idx = {r["Txn ID"]: i for i, r in enumerate(raw)}

    for r in debit_rows:
        idx = list(raw).index(r) if r in raw else None
        # Find by index in normalised list (normalisation order = CSV row order)
        row_idx = raw.index(r)
        tx = txs[row_idx]
        assert tx.amount is not None and tx.amount < 0, (
            f"Expected debit row to have negative amount, got {tx.amount}"
        )

    for r in credit_rows:
        row_idx = raw.index(r)
        tx = txs[row_idx]
        assert tx.amount is not None and tx.amount > 0, (
            f"Expected credit row to have positive amount, got {tx.amount}"
        )

def test_integration_ledger():
    with open("data/raw/merchant_ledger.csv", "r") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
        columns = reader.fieldnames
        
    mapper = SchemaMapper(MockLLMProvider())
    mapping = mapper.map_source("ledger", columns, [])
    
    norm = Normalizer()
    txs = norm.normalize(raw, mapping)
    assert len(txs) > 0
    for tx in txs:
        assert str(tx.source) == "ledger"
