"""
Reconciliation Pipeline — Milestone 5

Orchestrates the full reconciliation flow:
    deterministic matching → optional LLM arbitration → final result

The final result is a structured `FinalReconciliationResult` that exposes
decisions, exceptions, and audit records in a single consumable object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models.canonical import (
    AuditRecord,
    CanonicalTransaction,
    ExceptionRecord,
    ReconciliationDecision,
)
from app.services.arbitrator import LLMArbitrationService
from app.services.matcher import DeterministicMatcher, MatchResult


@dataclass
class FinalReconciliationResult:
    """Thin wrapper over the reconciliation output.

    Downstream consumers (match-rate reporting, dashboards, Q&A) should depend
    on this structure rather than reconstructing results from internal state.
    """

    decisions: list[ReconciliationDecision] = field(default_factory=list)
    exceptions: list[ExceptionRecord] = field(default_factory=list)
    audit_records: list[AuditRecord] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def matched_decisions(self) -> list[ReconciliationDecision]:
        return [d for d in self.decisions if d.decision == "matched"]

    @property
    def ambiguous_decisions(self) -> list[ReconciliationDecision]:
        return [d for d in self.decisions if d.decision == "ambiguous"]

    @property
    def unmatched_decisions(self) -> list[ReconciliationDecision]:
        return [d for d in self.decisions if d.decision == "unmatched"]

    def match_rate(self) -> float:
        if not self.decisions:
            return 0.0
        return len(self.matched_decisions) / len(self.decisions)


def reconcile(
    source_records: list[CanonicalTransaction],
    target_records: list[CanonicalTransaction],
    arbitrator: Optional[LLMArbitrationService] = None,
) -> FinalReconciliationResult:
    """Run deterministic matching and optionally resolve ambiguities via LLM.

    Flow:
        1. DeterministicMatcher produces MatchResult (decisions + exceptions + audits).
        2. If an arbitrator is provided, only ambiguous decisions are sent to it.
        3. The arbitrator validates provider output and preserves deterministic evidence.
        4. A FinalReconciliationResult is returned with all three collections.

    Matched and unmatched decisions are never sent to arbitration.
    """
    matcher = DeterministicMatcher()
    result: MatchResult = matcher.match(source_records, target_records)

    if arbitrator is not None:
        result = arbitrator.process_match_result(result, source_records, target_records)

    return FinalReconciliationResult(
        decisions=result.decisions,
        exceptions=result.exceptions,
        audit_records=result.audit_records,
    )
