import uuid
import logging
from pydantic import ValidationError

from app.models.canonical import CanonicalTransaction, ReconciliationDecision, ExceptionRecord, AuditRecord
from app.services.matcher import MatchResult
from app.models.arbitration import LLMArbitrationDecision
from app.services.arbitration_provider import ArbitrationProvider

logger = logging.getLogger(__name__)


def _make_id() -> str:
    return str(uuid.uuid4())


class LLMArbitrationService:
    """Service to handle LLM arbitration for ambiguous deterministic matches.
    It validates provider output, preserves deterministic evidence, and records
    resolution information on any existing ExceptionRecord.
    """

    def __init__(self, provider: ArbitrationProvider):
        self.provider = provider

    def process_match_result(
        self,
        match_result: MatchResult,
        source_records: list[CanonicalTransaction],
        target_records: list[CanonicalTransaction]
    ) -> MatchResult:
        """Process a deterministic MatchResult.
        Only 'ambiguous' decisions are sent to the provider.
        """
        source_map = {tx.record_id: tx for tx in source_records}
        target_map = {tx.record_id: tx for tx in target_records}

        for decision in match_result.decisions:
            if decision.decision != "ambiguous":
                continue

            original_evidence = decision.evidence or {}
            candidate_ids = original_evidence.get("candidate_record_ids", [])
            if not candidate_ids:
                # No candidates listed – nothing to arbitrate.
                continue

            candidates = [target_map[cid] for cid in candidate_ids if cid in target_map]
            source_record = source_map.get(decision.source_record_id)
            if not source_record:
                continue

            # -----------------------------------------------------------------
            # 1. Invoke Provider (untrusted)
            # -----------------------------------------------------------------
            try:
                raw_response = self.provider.resolve_ambiguity(
                    source_record=source_record,
                    candidates=candidates,
                    deterministic_evidence=original_evidence,
                )
            except Exception as e:
                logger.error(f"Provider crashed on {decision.source_record_id}: {e}")
                continue  # keep original ambiguous decision

            # -----------------------------------------------------------------
            # 2. Validate provider output via Pydantic model
            # -----------------------------------------------------------------
            try:
                llm_decision = LLMArbitrationDecision.model_validate(raw_response)
            except ValidationError as ve:
                logger.error(f"Provider output validation failed: {ve}")
                continue  # keep original ambiguous decision

            # -----------------------------------------------------------------
            # 3. Verify candidate ID belongs to the original candidate pool
            # -----------------------------------------------------------------
            if llm_decision.decision == "matched":
                if llm_decision.candidate_record_id not in candidate_ids:
                    logger.error(
                        f"Provider hallucinated candidate ID: {llm_decision.candidate_record_id}"
                    )
                    continue  # keep original ambiguous decision

            # -----------------------------------------------------------------
            # 4. Preserve deterministic evidence and add LLM evidence
            # -----------------------------------------------------------------
            # Make a shallow copy to avoid accidental overwrites of the original dict
            preserved_evidence = dict(original_evidence)
            preserved_evidence["llm_evidence"] = llm_decision.evidence
            # Keep a reference to the deterministic method that produced ambiguity
            preserved_evidence["prior_deterministic_method"] = preserved_evidence.get("matched_via") or "ambiguous"

            # -----------------------------------------------------------------
            # 5. Update decision based on LLM outcome
            # -----------------------------------------------------------------
            if llm_decision.decision == "matched":
                decision.decision = "matched"
                decision.candidate_record_id = llm_decision.candidate_record_id
                decision.method = "llm_arbitration"
                decision.confidence = llm_decision.confidence
                decision.reason = f"[LLM] {llm_decision.reason}"
                decision.evidence = preserved_evidence

                # Mark any existing exception as resolved via evidence
                for exc in match_result.exceptions:
                    if exc.record_id == decision.source_record_id:
                        # Add resolution info to the exception's evidence dict
                        exc.evidence = dict(exc.evidence)  # copy
                        exc.evidence["resolved_by"] = "llm_arbitration"
                        exc.evidence["resolution_reason"] = llm_decision.reason

                match_result.audit_records.append(
                    AuditRecord(
                        audit_id=_make_id(),
                        record_id=source_record.record_id,
                        stage="llm_arbitration",
                        action="resolved_match",
                        method="llm_arbitration",
                        decision="matched",
                        evidence=llm_decision.model_dump(),
                    )
                )
            else:  # ambiguous remains ambiguous
                decision.method = "llm_arbitration"
                decision.confidence = llm_decision.confidence
                decision.reason = f"[LLM] {llm_decision.reason}"
                decision.evidence = preserved_evidence

                match_result.audit_records.append(
                    AuditRecord(
                        audit_id=_make_id(),
                        record_id=source_record.record_id,
                        stage="llm_arbitration",
                        action="remained_ambiguous",
                        method="llm_arbitration",
                        decision="ambiguous",
                        evidence=llm_decision.model_dump(),
                    )
                )

        # ---------------------------------------------------------------------
        # Ensure every source record has at least one audit entry (no blanket fallback)
        # ---------------------------------------------------------------------
        audited_ids = {audit.record_id for audit in match_result.audit_records}
        for src in source_records:
            if src.record_id not in audited_ids:
                # Create a precise audit reflecting the deterministic decision
                related_decision = next(
                    (d for d in match_result.decisions if d.source_record_id == src.record_id),
                    None,
                )
                action = related_decision.method if related_decision else "unknown"
                match_result.audit_records.append(
                    AuditRecord(
                        audit_id=_make_id(),
                        record_id=src.record_id,
                        stage="deterministic_matching",
                        action=action,
                        method=action,
                        decision=related_decision.decision if related_decision else "unmatched",
                        evidence=related_decision.evidence if related_decision else {},
                    )
                )

        return match_result
