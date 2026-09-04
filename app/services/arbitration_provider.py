from abc import ABC, abstractmethod
from typing import Any
from app.models.canonical import CanonicalTransaction


class ArbitrationProvider(ABC):
    """Abstract interface for LLM arbitration providers."""

    @abstractmethod
    def resolve_ambiguity(
        self,
        source_record: CanonicalTransaction,
        candidates: list[CanonicalTransaction],
        deterministic_evidence: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Produce a raw dictionary representing the arbitration decision.
        The service is responsible for parsing and validating this output.
        """
        raise NotImplementedError


class MockArbitrationProvider(ArbitrationProvider):
    """Mock implementation for deterministic testing."""

    def __init__(self, override_response: dict[str, Any] | None = None):
        """
        We can force the mock to return a known invalid or valid dict
        in tests by supplying override_response.
        """
        self.override_response = override_response
        self.call_count = 0
        self.last_source = None
        self.last_candidates = None
        
    def resolve_ambiguity(
        self,
        source_record: CanonicalTransaction,
        candidates: list[CanonicalTransaction],
        deterministic_evidence: dict[str, Any]
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_source = source_record
        self.last_candidates = candidates
        
        if self.override_response is not None:
            return self.override_response
            
        # Default mock behaviour: If first candidate has gross matching amount, pick it.
        # Ensure it's not guessing, just applying a safe mock logic.
        if candidates and source_record.amount and candidates[0].amount == source_record.amount:
            return {
                "decision": "matched",
                "candidate_record_id": candidates[0].record_id,
                "confidence": 0.8,
                "reason": "Mocked match based on amount.",
                "evidence": {"provider": "MockArbitrationProvider"}
            }
            
        # Default fallback
        return {
            "decision": "ambiguous",
            "candidate_record_id": None,
            "confidence": 0.4,
            "reason": "Mocked ambiguous decision.",
            "evidence": {"provider": "MockArbitrationProvider"}
        }
