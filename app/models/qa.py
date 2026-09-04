import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntentDefinition(str, enum.Enum):
    RESOLUTION_SUMMARY = "resolution_summary"
    UNRESOLVED_RECORDS = "unresolved_records"
    TRANSACTION_EXPLANATION = "transaction_explanation"
    SETTLEMENT_TOTAL = "settlement_total"
    FEE_TOTAL = "fee_total"
    TAX_TOTAL = "tax_total"
    FEE_AND_TAX_TOTAL = "fee_and_tax_total"
    REFUNDS = "refunds"
    BATCH_SETTLEMENTS = "batch_settlements"
    REFERENCE_LOOKUP = "reference_lookup"
    UNSUPPORTED = "unsupported"


class ParsedCommand(BaseModel):
    intent: IntentDefinition
    record_id: Optional[str] = None
    reference: Optional[str] = None
    date: Optional[str] = None


class GroundedFactSet(BaseModel):
    question: str
    intent: IntentDefinition
    record_ids: List[str] = Field(default_factory=list)
    numerical_values: List[float] = Field(default_factory=list)
    facts: Dict[str, Any] = Field(default_factory=dict)
    insufficient_evidence: bool = False


class GroundedAnswer(BaseModel):
    answer: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
