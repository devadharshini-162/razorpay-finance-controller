from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Any
from app.models.canonical import CanonicalTransaction

class MappingResult(BaseModel):
    """Represents the semantic mapping from source columns to canonical concepts."""
    source_name: str
    column_mapping: Dict[str, str] = Field(..., description="Mapping from raw column name to canonical field name")
    unmapped_columns: List[str] = Field(default_factory=list, description="Columns that could not be semantically mapped")
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: Optional[str] = None
    audit_info: Dict[str, Any] = Field(default_factory=dict, description="Audit/traceability info about the mapping decision")

    model_config = {
        "extra": "forbid"
    }

    @model_validator(mode='after')
    def validate_canonical_fields(self):
        canonical_fields = set(CanonicalTransaction.model_fields.keys())
        for col, map_target in self.column_mapping.items():
            if map_target not in canonical_fields:
                raise ValueError(f"Invalid mapping target: {map_target}")
        return self
