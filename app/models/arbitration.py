from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

class LLMArbitrationDecision(BaseModel):
    """Structured output expected from the LLM arbitration provider."""
    
    decision: Literal["matched", "ambiguous"]
    candidate_record_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "extra": "forbid"
    }

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == "matched" and not self.candidate_record_id:
            raise ValueError("candidate_record_id MUST be present if decision is 'matched'")
        if self.decision == "ambiguous" and self.candidate_record_id:
            raise ValueError("candidate_record_id MUST be explicitly null/absent if decision is 'ambiguous'")
        return self
