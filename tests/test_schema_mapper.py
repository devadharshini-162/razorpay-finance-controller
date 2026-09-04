import pytest
from app.models.mapping import MappingResult
from app.services.schema_mapper import SchemaMapper, MockLLMProvider
from pydantic import ValidationError

def test_schema_mapper_razorpay():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Settlement Ref", "Order Reference", "Gross", "Processing Fee", "GST", "Settled Amount", "Settlement Date", "UTR"]
    result = schema_mapper.map_source("razorpay", columns, [])
    assert result.column_mapping["Settlement Ref"] == "settlement_id"
    assert result.column_mapping["Order Reference"] == "order_id"
    assert result.column_mapping["Settled Amount"] == "amount"
    assert result.column_mapping["Settlement Date"] == "settlement_date"

def test_schema_mapper_bank():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Txn Date", "Narration", "Credit", "Debit", "Bank Ref", "Running Balance"]
    result = schema_mapper.map_source("bank", columns, [])

    assert result.column_mapping["Txn Date"] == "posted_date"
    assert result.column_mapping["Credit"] == "amount"
    assert result.column_mapping["Debit"] == "amount"   # Both map to amount; sign applied at normalisation
    assert result.column_mapping["Bank Ref"] == "reference"
    assert result.column_mapping["Narration"] == "description"
    assert "Running Balance" in result.unmapped_columns
    
def test_schema_mapper_ledger():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Invoice No", "Paid On", "Customer", "Amount Received", "Remarks"]
    result = schema_mapper.map_source("ledger", columns, [])
    
    assert result.column_mapping["Invoice No"] == "reference"
    assert result.column_mapping["Amount Received"] == "amount"

def test_schema_mapper_unfamiliar_fourth_schema():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Ref No", "Value Dt", "Particular", "Credit Amt", "Customer Name"]
    result = schema_mapper.map_source("dummy_fourth", columns, [])
    
    assert result.column_mapping["Ref No"] == "reference"
    assert result.column_mapping["Value Dt"] == "posted_date"
    assert result.column_mapping["Particular"] == "description"
    assert result.column_mapping["Credit Amt"] == "amount"
    assert result.column_mapping["Customer Name"] == "counterparty"

def test_schema_mapper_missing_optional():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Settled Amount", "Settlement Date"]
    result = schema_mapper.map_source("razorpay_sparse", columns, [])
    assert result.column_mapping["Settled Amount"] == "amount"
    assert "UTR" not in result.column_mapping

def test_schema_mapper_preserves_unmapped():
    schema_mapper = SchemaMapper(MockLLMProvider())
    columns = ["Settled Amount", "Random Unrelated Field"]
    result = schema_mapper.map_source("razorpay_sparse", columns, [])
    assert "Random Unrelated Field" in result.unmapped_columns

def test_mapper_contract_rejects_invalid_target():
    """A mapping target that is not a real CanonicalTransaction field must be rejected."""
    with pytest.raises(ValidationError):
        MappingResult(
            source_name="test",
            column_mapping={"Col A": "not_a_real_canonical_field"},
            confidence=0.9
        )

def test_mapper_contract_validation():
    with pytest.raises(ValidationError):
        MappingResult(source_name="bad", column_mapping={"a": "b"}, confidence=2.0)

    with pytest.raises(ValidationError):
        MappingResult(source_name="bad", column_mapping={"a": "b"}, confidence=1.0, bad_field="test")
