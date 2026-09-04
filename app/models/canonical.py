from decimal import Decimal
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class CanonicalTransaction(BaseModel):
    """Represents a normalized source transaction record."""
    record_id: str
    source: str
    transaction_type: Literal[
        "payment",
        "settlement",
        "refund",
        "adjustment",
        "transfer",
        "unknown"
    ]

    transaction_id: str | None = None
    order_id: str | None = None
    settlement_id: str | None = None
    reference: str | None = None

    amount: Decimal | None = None
    gross_amount: Decimal | None = None
    fee: Decimal | None = None
    tax: Decimal | None = None
    adjustment: Decimal | None = None
    refund_amount: Decimal | None = None
    currency: str | None = None

    transaction_date: date | None = None
    settlement_date: date | None = None
    posted_date: date | None = None

    counterparty: str | None = None
    description: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid"
    }


class ReconciliationDecision(BaseModel):
    """Represents the conclusion produced by the reconciliation engine for a source record."""
    decision_id: str
    source_record_id: str
    candidate_record_id: str | None = None

    decision: Literal[
        "matched",
        "unmatched",
        "ambiguous"
    ]

    method: str

    confidence: float = Field(ge=0.0, le=1.0)

    reason: str | None = None

    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid"
    }


class ExceptionRecord(BaseModel):
    """Represents a reconciliation exception."""
    exception_id: str
    record_id: str

    category: Literal[
        "missing_record",
        "amount_difference",
        "date_mismatch",
        "duplicate",
        "ambiguous_match",
        "batch_settlement",
        "refund_mismatch",
        "unknown"
    ]

    severity: Literal[
        "low",
        "medium",
        "high"
    ]

    reason: str

    confidence: float = Field(ge=0.0, le=1.0)

    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid"
    }


class AuditRecord(BaseModel):
    """Represents an auditable action/decision taken by the reconciliation pipeline."""
    audit_id: str
    record_id: str

    stage: str
    action: str
    method: str
    decision: str

    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid"
    }
