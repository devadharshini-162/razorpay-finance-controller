from typing import List, Dict, Any
from app.models.mapping import MappingResult

class LLMProvider:
    """Abstract interface for LLM schema mapping providers."""
    def map_schema(self, source_name: str, columns: List[str], sample_rows: List[Dict[str, Any]]) -> MappingResult:
        raise NotImplementedError

class MockLLMProvider(LLMProvider):
    """Mock implementation for testing and development logic."""
    def map_schema(self, source_name: str, columns: List[str], sample_rows: List[Dict[str, Any]]) -> MappingResult:
        mapping = {}
        unmapped = []
        
        # Simple heuristic mock
        for col in columns:
            cl = col.lower()
            if cl in ["ref no", "invoice no", "external ref"]:
                mapping[col] = "reference"
            elif "settlement ref" in cl or cl == "txn id" or ("payout" in cl and ("no" in cl or "id" in cl or "ref" in cl)):
                mapping[col] = "settlement_id" if ("settlement" in cl or "payout" in cl) else "transaction_id"
            elif "order reference" in cl:
                mapping[col] = "order_id"
            elif "gross" in cl:
                mapping[col] = "gross_amount"
            elif "processing charges" in cl or "processing fee" in cl or "fee" == cl.strip():
                mapping[col] = "fee"
            elif "gst" in cl or "tax" == cl.strip():
                mapping[col] = "tax"
            elif "net payout" in cl or "settled amount" in cl or "credit" == cl.strip() or "debit" == cl.strip() or "amount received" in cl or "credit amt" in cl or "debit amt" in cl:
                mapping[col] = "amount"
            elif "date" in cl or "dt" in cl or "paid on" in cl or "created at" in cl:
                if "settlement" in cl or "effective" in cl:
                    mapping[col] = "settlement_date"
                elif "txn" in cl or "value" in cl:
                    mapping[col] = "posted_date"
                else:
                    mapping[col] = "transaction_date"
            elif "utr" in cl or cl == "bank ref":
                mapping[col] = "reference"
            elif "particular" in cl or "narration" in cl or "remarks" in cl or "narrative" in cl:
                mapping[col] = "description"
            elif "customer" in cl or "beneficiary" in cl:
                mapping[col] = "counterparty"
            else:
                unmapped.append(col)

        return MappingResult(
            source_name=source_name,
            column_mapping=mapping,
            unmapped_columns=unmapped,
            confidence=0.9,
            explanation="Mocked mapping logic based on column substring analysis",
            audit_info={"provider": "MockLLMProvider"}
        )

# TODO: Create a production provider class using the Gemini/OpenAI API that implements LLMProvider

class SchemaMapper:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        
    def map_source(self, source_name: str, columns: List[str], sample_rows: List[Dict[str, Any]]) -> MappingResult:
        return self.provider.map_schema(source_name, columns, sample_rows)
