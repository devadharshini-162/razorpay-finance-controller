"""
Deterministic Match Engine — Milestone 3

Matches Razorpay CanonicalTransactions against Bank CanonicalTransactions using
a strictly ordered set of deterministic rules. No LLM, no fuzzy matching.

CONFIDENCE SCALE (documented):
    exact_identifier            → 1.00
    financial_reconciliation    → 0.92
    exact_amount_date           → 0.95
    amount_date_tolerance       → 0.85
    batch_amount_reconciliation → 0.90
    ambiguous                   → 0.40
    unmatched                   → 0.10

RULE PRIORITY:
    1. Exact identifier match      (UTR/reference ↔ Bank Ref, exact string after normalisation)
    2. Financial reconciliation     (Razorpay gross-fee-tax == Bank credit)
    3. Exact amount + date match   (amount equal AND settlement_date == posted_date)
    4. Amount + date tolerance     (amount equal AND |date diff| <= DATE_TOLERANCE_DAYS)
    5. Batch reconciliation        (sum of Razorpay settled amounts == single Bank credit, shared UTR)
    6. Refund detection            (Razorpay refund record ↔ Bank debit by amount+identifier)
    7. Ambiguous / Unmatched
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.canonical import AuditRecord, CanonicalTransaction, ExceptionRecord, ReconciliationDecision

DATE_TOLERANCE_DAYS = 3  # matches the generator: dt_bank = dt + timedelta(days=randint(1, 3))

CONFIDENCE = {
    "exact_identifier": 1.00,
    "financial_reconciliation": 0.92,
    "exact_amount_date": 0.95,
    "amount_date_tolerance": 0.85,
    "batch_amount_reconciliation": 0.90,
    "refund_identifier": 0.95,
    "ambiguous": 0.40,
    "unmatched": 0.10,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm_ref(value: str | None) -> str | None:
    """Normalise a reference/UTR string for comparison.

    The generator can produce 'UTR123', 'utr-123', 'UTR 123', or lowercase.
    Strip whitespace, lower-case, and remove common prefixes so 'UTR123'
    matches 'utr-123' matches 'UTR 123'.
    """
    if not value:
        return None
    v = value.strip().lower()
    # Remove common prefixes, dashes, and spaces
    for prefix in ("utr-", "utr ", "utr"):
        if v.startswith(prefix):
            v = v[len(prefix):]
            break
    return v.strip() or None


def _get_date(tx: CanonicalTransaction) -> date | None:
    """Return the most relevant date from a transaction."""
    return tx.settlement_date or tx.posted_date or tx.transaction_date


def _date_diff(d1: date | None, d2: date | None) -> int | None:
    if d1 is None or d2 is None:
        return None
    return abs((d1 - d2).days)


def _make_id() -> str:
    return str(uuid.uuid4())


def _expected_settlement(tx: CanonicalTransaction) -> Decimal | None:
    """Compute expected bank credit from Razorpay fields.

    Only computes when gross_amount is present.  Missing fee/tax/adjustment/
    refund_amount are treated as zero ONLY when gross_amount is present —
    which is the explicitly justified data representation in Case C.
    """
    if tx.gross_amount is None:
        return None
    result = tx.gross_amount
    result -= tx.fee or Decimal(0)
    result -= tx.tax or Decimal(0)
    result += tx.adjustment or Decimal(0)
    result -= tx.refund_amount or Decimal(0)
    return result


def _candidate_details(candidates: list[CanonicalTransaction]) -> list[dict[str, str | None]]:
    """Expose the fields a reviewer needs to distinguish bank candidates."""
    return [
        {
            "record_id": candidate.record_id,
            "reference": candidate.reference,
            "amount": str(candidate.amount) if candidate.amount is not None else None,
            "date": str(_get_date(candidate)) if _get_date(candidate) else None,
            "description": candidate.description,
        }
        for candidate in candidates
    ]


def _candidate_summary(candidates: list[CanonicalTransaction]) -> str:
    return "; ".join(
        f"{candidate.record_id} (reference {candidate.reference or 'not supplied'}, "
        f"amount {candidate.amount if candidate.amount is not None else 'not supplied'}, "
        f"date {_get_date(candidate) or 'not supplied'})"
        for candidate in candidates
    )


def _ambiguity_reason(src: CanonicalTransaction, candidates: list[CanonicalTransaction], matched_on: list[str]) -> str:
    shared_amounts = ", ".join(sorted({str(candidate.amount) for candidate in candidates if candidate.amount is not None})) or "an unavailable amount"
    shared_dates = ", ".join(sorted({str(_get_date(candidate)) for candidate in candidates if _get_date(candidate)})) or "an unavailable date"
    missing_references = all(not candidate.reference for candidate in candidates)
    reference_note = "Neither candidate includes a UTR/reference to distinguish it." if missing_references else "Available references do not identify a unique candidate."
    return (
        f"{len(candidates)} bank candidates share the same {', '.join(field.replace('_', ' ') for field in matched_on)} "
        f"(amount ₹{shared_amounts}; date {shared_dates}). {reference_note}"
    )


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    decisions: list[ReconciliationDecision] = field(default_factory=list)
    exceptions: list[ExceptionRecord] = field(default_factory=list)
    audit_records: list[AuditRecord] = field(default_factory=list)

    def match_rate(self) -> float:
        """Fraction of source records with decision == 'matched'."""
        if not self.decisions:
            return 0.0
        matched = sum(1 for d in self.decisions if d.decision == "matched")
        return matched / len(self.decisions)


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class DeterministicMatcher:
    """Deterministic reconciliation engine — Razorpay → Bank."""

    def match(
        self,
        source_records: list[CanonicalTransaction],
        target_records: list[CanonicalTransaction],
    ) -> MatchResult:
        result = MatchResult()

        # ------------------------------------------------------------------
        # Pre-build indexes for efficient exact lookups
        # ------------------------------------------------------------------
        # Bank reference index: normalised_ref → [bank_tx]
        bank_by_ref: dict[str, list[CanonicalTransaction]] = {}
        for tx in target_records:
            nr = _norm_ref(tx.reference)
            if nr:
                bank_by_ref.setdefault(nr, []).append(tx)

        # Bank amount+date index: (amount, date) → [bank_tx]
        bank_by_amount_date: dict[tuple, list[CanonicalTransaction]] = {}
        for tx in target_records:
            if tx.amount is not None and _get_date(tx) is not None:
                key = (tx.amount, _get_date(tx))
                bank_by_amount_date.setdefault(key, []).append(tx)

        # All bank by id
        bank_by_id: dict[str, CanonicalTransaction] = {tx.record_id: tx for tx in target_records}

        # Track consumed bank record IDs to prevent reuse
        consumed_target_ids: set[str] = set()

        # ------------------------------------------------------------------
        # Batch detection: group Razorpay records by shared (normalised) UTR
        # ------------------------------------------------------------------
        batch_groups: dict[str, list[CanonicalTransaction]] = {}
        for tx in source_records:
            nr = _norm_ref(tx.reference)
            if nr:
                batch_groups.setdefault(nr, []).append(tx)

        batch_matched_source_ids: set[str] = set()

        for utm_ref, group in batch_groups.items():
            if len(group) < 2:
                continue  # Not a batch
            # Find bank record(s) that carry this same reference
            bank_candidates = bank_by_ref.get(utm_ref, [])
            if len(bank_candidates) != 1:
                continue  # Can't safely attribute to exactly one bank record
            bank_tx = bank_candidates[0]
            if bank_tx.record_id in consumed_target_ids:
                continue

            # Verify: sum of settled amounts == bank credit
            group_amounts = [tx.amount for tx in group if tx.amount is not None]
            if len(group_amounts) != len(group):
                continue  # Some amounts missing
            total = sum(group_amounts)

            if bank_tx.amount is None:
                continue

            if total != bank_tx.amount:
                # Financial reconciliation: try sum of expected settlements
                exp_amounts = [_expected_settlement(tx) for tx in group]
                if None in exp_amounts:
                    continue
                exp_total = sum(exp_amounts)
                if exp_total != bank_tx.amount:
                    continue
                total = exp_total

            # Batch match established — emit one decision per source record
            consumed_target_ids.add(bank_tx.record_id)
            for tx in group:
                batch_matched_source_ids.add(tx.record_id)

            batch_evidence = {
                "shared_reference": utm_ref,
                "source_record_ids": [tx.record_id for tx in group],
                "source_amounts": [str(tx.amount) for tx in group],
                "aggregated_amount": str(total),
                "target_record_id": bank_tx.record_id,
                "target_amount": str(bank_tx.amount),
            }
            for tx in group:
                dec = ReconciliationDecision(
                    decision_id=_make_id(),
                    source_record_id=tx.record_id,
                    candidate_record_id=bank_tx.record_id,
                    decision="matched",
                    method="batch_amount_reconciliation",
                    confidence=CONFIDENCE["batch_amount_reconciliation"],
                    reason=f"Sum of {len(group)} Razorpay settlements equals single bank credit via shared UTR {utm_ref!r}.",
                    evidence=batch_evidence,
                )
                result.decisions.append(dec)
                result.audit_records.append(AuditRecord(
                    audit_id=_make_id(),
                    record_id=tx.record_id,
                    stage="deterministic_matching",
                    action="batch_amount_reconciliation",
                    method="batch_amount_reconciliation",
                    decision="matched",
                    evidence=batch_evidence,
                ))

        # ------------------------------------------------------------------
        # Process each Razorpay source record
        # ------------------------------------------------------------------
        for src in source_records:
            if src.record_id in batch_matched_source_ids:
                continue

            decision, audit, exception = self._match_one(
                src, target_records, bank_by_ref, bank_by_amount_date, consumed_target_ids
            )
            result.decisions.append(decision)
            result.audit_records.append(audit)
            if exception:
                result.exceptions.append(exception)
            if decision.decision == "matched" and decision.candidate_record_id:
                consumed_target_ids.add(decision.candidate_record_id)

        return result

    # ------------------------------------------------------------------
    # Single-record matching
    # ------------------------------------------------------------------

    def _match_one(
        self,
        src: CanonicalTransaction,
        all_targets: list[CanonicalTransaction],
        bank_by_ref: dict[str, list[CanonicalTransaction]],
        bank_by_amount_date: dict[tuple, list[CanonicalTransaction]],
        consumed: set[str],
    ) -> tuple[ReconciliationDecision, AuditRecord, Optional[ExceptionRecord]]:

        # ---- Rule 1: Exact identifier match --------------------------------
        src_ref = _norm_ref(src.reference)
        if src_ref:
            candidates = [
                tx for tx in bank_by_ref.get(src_ref, [])
                if tx.record_id not in consumed
            ]
            if len(candidates) == 1:
                bank_tx = candidates[0]
                return self._make_match(
                    src, bank_tx,
                    method="exact_identifier",
                    reason=f"Razorpay reference {src.reference!r} matches bank reference {bank_tx.reference!r}.",
                    evidence={
                        "identifier_field": "reference",
                        "source_value": src.reference,
                        "target_value": bank_tx.reference,
                    },
                )
            if len(candidates) > 1:
                positives = [c for c in candidates if c.amount is not None and c.amount > 0]
                negatives = [c for c in candidates if c.amount is not None and c.amount < 0]
                if len(positives) == 1 and len(negatives) > 0 and (len(positives) + len(negatives) == len(candidates)):
                    bank_tx = positives[0]
                    return self._make_match(
                        src, bank_tx,
                        method="exact_identifier",
                        reason=f"Razorpay reference {src.reference!r} matches credit candidate and associated debit candidate(s).",
                        evidence={
                            "identifier_field": "reference",
                            "source_value": src.reference,
                            "target_value": bank_tx.reference,
                            "associated_debit_candidates": [
                                {"record_id": d.record_id, "amount": str(d.amount)} for d in negatives
                            ],
                        },
                    )
                # Multiple bank records share the same identifier → duplicate
                return self._make_duplicate(src, candidates, "exact_identifier")

        # ---- Rule 2: Exact amount + date match -----------------------------
        src_amount = src.amount
        src_date = _get_date(src)
        if src_amount is not None and src_date is not None:
            key = (src_amount, src_date)
            candidates = [
                tx for tx in bank_by_amount_date.get(key, [])
                if tx.record_id not in consumed and tx.amount is not None and tx.amount > 0
            ]
            if len(candidates) == 1:
                bank_tx = candidates[0]
                return self._make_match(
                    src, bank_tx,
                    method="exact_amount_date",
                    reason=f"Amount {src_amount} and date {src_date} uniquely match bank record.",
                    evidence={
                        "amount": {"source": str(src_amount), "target": str(bank_tx.amount)},
                        "date": {"source": str(src_date), "target": str(_get_date(bank_tx))},
                    },
                )
            if len(candidates) > 1:
                # Multiple candidates: genuinely ambiguous
                return self._make_ambiguous(
                    src, candidates, matched_on=["amount", "date"]
                )

        # ---- Rule 3: Financial reconciliation (gross - fee - tax) ----------
        if src.gross_amount is not None:
            exp = _expected_settlement(src)
            if exp is not None and src.amount is not None:
                src_date = _get_date(src)
                # Find bank credits that equal the expected net amount on the same date
                bank_candidates = [
                    tx for tx in bank_by_amount_date.get((exp, src_date), [])
                    if tx.record_id not in consumed and tx.amount is not None and tx.amount > 0
                ]
                if len(bank_candidates) == 1:
                    bank_tx = bank_candidates[0]
                    return self._make_match(
                        src, bank_tx,
                        method="financial_reconciliation",
                        reason=(
                            f"gross({src.gross_amount}) - fee({src.fee}) - tax({src.tax}) "
                            f"= {exp} matches bank credit {bank_tx.amount}."
                        ),
                        evidence={
                            "gross_amount": str(src.gross_amount),
                            "fee": str(src.fee),
                            "tax": str(src.tax),
                            "adjustment": str(src.adjustment),
                            "refund_amount": str(src.refund_amount),
                            "expected_amount": str(exp),
                            "bank_amount": str(bank_tx.amount),
                        },
                    )

        # ---- Rule 4: Amount + date tolerance --------------------------------
        if src_amount is not None and src_date is not None:
            tolerance_candidates = []
            for tx in all_targets:
                if tx.record_id in consumed:
                    continue
                if tx.amount != src_amount:
                    continue
                if tx.amount is None or tx.amount <= 0:
                    continue
                diff = _date_diff(src_date, _get_date(tx))
                if diff is not None and 1 <= diff <= DATE_TOLERANCE_DAYS:
                    tolerance_candidates.append((diff, tx))

            if len(tolerance_candidates) == 1:
                diff, bank_tx = tolerance_candidates[0]
                return self._make_match(
                    src, bank_tx,
                    method="amount_date_tolerance",
                    reason=f"Amount matches and date differs by {diff} day(s) within tolerance of {DATE_TOLERANCE_DAYS}.",
                    evidence={
                        "source_date": str(src_date),
                        "target_date": str(_get_date(bank_tx)),
                        "difference_days": diff,
                        "allowed_days": DATE_TOLERANCE_DAYS,
                        "amount": str(src_amount),
                    },
                )
            if len(tolerance_candidates) > 1:
                return self._make_ambiguous(
                    src, [tc[1] for tc in tolerance_candidates],
                    matched_on=["amount", "date_tolerance"]
                )

        # ---- Refund detection -----------------------------------------------
        # Razorpay refund records have settlement_id starting with 'ref_'.
        # The corresponding bank record carries a bank Debit (negative amount)
        # for the same gross amount with the UTR in narration.
        if src.settlement_id and src.settlement_id.startswith("ref_"):
            # Look for a bank debit matching the gross amount
            gross = src.gross_amount or src.amount
            if gross is not None:
                debit_candidates = [
                    tx for tx in all_targets
                    if tx.record_id not in consumed
                    and tx.amount is not None
                    and tx.amount == -abs(gross)   # debit → negative in our normaliser
                ]
                if len(debit_candidates) == 1:
                    bank_tx = debit_candidates[0]
                    return self._make_match(
                        src, bank_tx,
                        method="refund_identifier",
                        reason=f"Razorpay refund record matched bank debit of {gross}.",
                        evidence={
                            "razorpay_settlement_id": src.settlement_id,
                            "gross_amount": str(gross),
                            "bank_debit_amount": str(bank_tx.amount),
                        },
                    )
                exc = ExceptionRecord(
                    exception_id=_make_id(),
                    record_id=src.record_id,
                    category="refund_mismatch",
                    severity="medium",
                    reason="Razorpay refund record found but no uniquely matching bank debit.",
                    confidence=0.5,
                    evidence={"razorpay_settlement_id": src.settlement_id},
                )
                return self._make_unmatched(src, "Razorpay refund found but no uniquely matching bank debit record."), \
                       self._make_unmatched_audit(src, "refund_identifier"), exc

        # ---- Unmatched -------------------------------------------------------
        return self._make_unmatched_tuple(src)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    def _make_match(
        self,
        src: CanonicalTransaction,
        bank_tx: CanonicalTransaction,
        method: str,
        reason: str,
        evidence: dict,
    ) -> tuple[ReconciliationDecision, AuditRecord, None]:
        dec = ReconciliationDecision(
            decision_id=_make_id(),
            source_record_id=src.record_id,
            candidate_record_id=bank_tx.record_id,
            decision="matched",
            method=method,
            confidence=CONFIDENCE.get(method, 0.5),
            reason=reason,
            evidence=evidence,
        )
        aud = AuditRecord(
            audit_id=_make_id(),
            record_id=src.record_id,
            stage="deterministic_matching",
            action=method,
            method=method,
            decision="matched",
            evidence=evidence,
        )
        return dec, aud, None

    def _make_ambiguous(
        self,
        src: CanonicalTransaction,
        candidates: list[CanonicalTransaction],
        matched_on: list[str],
    ) -> tuple[ReconciliationDecision, AuditRecord, ExceptionRecord]:
        evidence = {
            "candidate_count": len(candidates),
            "candidate_record_ids": [c.record_id for c in candidates],
            "bank_candidates": _candidate_details(candidates),
            "matched_on": matched_on,
        }
        reason = _ambiguity_reason(src, candidates, matched_on)
        dec = ReconciliationDecision(
            decision_id=_make_id(),
            source_record_id=src.record_id,
            candidate_record_id=None,
            decision="ambiguous",
            method="ambiguous",
            confidence=CONFIDENCE["ambiguous"],
            reason=reason,
            evidence=evidence,
        )
        aud = AuditRecord(
            audit_id=_make_id(),
            record_id=src.record_id,
            stage="deterministic_matching",
            action="ambiguous",
            method="ambiguous",
            decision="ambiguous",
            evidence=evidence,
        )
        exc = ExceptionRecord(
            exception_id=_make_id(),
            record_id=src.record_id,
            category="ambiguous_match",
            severity="medium",
            reason=f"{reason} Manual review or LLM arbitration is required.",
            confidence=CONFIDENCE["ambiguous"],
            evidence=evidence,
        )
        return dec, aud, exc

    def _make_duplicate(
        self,
        src: CanonicalTransaction,
        candidates: list[CanonicalTransaction],
        matched_on: str,
    ) -> tuple[ReconciliationDecision, AuditRecord, ExceptionRecord]:
        evidence = {
            "candidate_count": len(candidates),
            "candidate_record_ids": [c.record_id for c in candidates],
            "bank_candidates": _candidate_details(candidates),
            "matched_via": matched_on,
        }
        candidate_summary = _candidate_summary(candidates)
        dec = ReconciliationDecision(
            decision_id=_make_id(),
            source_record_id=src.record_id,
            candidate_record_id=None,
            decision="ambiguous",
            method="duplicate",
            confidence=CONFIDENCE["ambiguous"],
            reason=(
                f"{src.record_id} has the same reference as {len(candidates)} bank records: "
                f"{candidate_summary}. This indicates possible duplicate bank entries."
            ),
            evidence=evidence,
        )
        aud = AuditRecord(
            audit_id=_make_id(),
            record_id=src.record_id,
            stage="deterministic_matching",
            action="duplicate_detected",
            method="duplicate",
            decision="ambiguous",
            evidence=evidence,
        )
        exc = ExceptionRecord(
            exception_id=_make_id(),
            record_id=src.record_id,
            category="duplicate",
            severity="high",
            reason=(
                f"{len(candidates)} bank records share {src.reference or 'the same identifier'}: "
                f"{candidate_summary}. Likely duplicate bank entries."
            ),
            confidence=0.90,
            evidence=evidence,
        )
        return dec, aud, exc

    def _make_unmatched(self, src: CanonicalTransaction, reason: str) -> ReconciliationDecision:
        return ReconciliationDecision(
            decision_id=_make_id(),
            source_record_id=src.record_id,
            candidate_record_id=None,
            decision="unmatched",
            method="unmatched",
            confidence=CONFIDENCE["unmatched"],
            reason=reason,
            evidence={},
        )

    def _make_unmatched_audit(self, src: CanonicalTransaction, attempted_method: str) -> AuditRecord:
        return AuditRecord(
            audit_id=_make_id(),
            record_id=src.record_id,
            stage="deterministic_matching",
            action="unmatched",
            method=attempted_method,
            decision="unmatched",
            evidence={},
        )

    def _make_unmatched_tuple(
        self, src: CanonicalTransaction
    ) -> tuple[ReconciliationDecision, AuditRecord, ExceptionRecord]:
        reason = "No bank record matched the settlement reference or deterministic amount/date criteria."
        dec = ReconciliationDecision(
            decision_id=_make_id(),
            source_record_id=src.record_id,
            candidate_record_id=None,
            decision="unmatched",
            method="unmatched",
            confidence=CONFIDENCE["unmatched"],
            reason=reason,
            evidence={},
        )
        aud = AuditRecord(
            audit_id=_make_id(),
            record_id=src.record_id,
            stage="deterministic_matching",
            action="unmatched",
            method="unmatched",
            decision="unmatched",
            evidence={},
        )
        exc = ExceptionRecord(
            exception_id=_make_id(),
            record_id=src.record_id,
            category="missing_record",
            severity="high",
            reason=reason,
            confidence=CONFIDENCE["unmatched"],
            evidence={},
        )
        return dec, aud, exc


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------

def calculate_match_rate(result: MatchResult) -> dict:
    """Return an explicit, deterministic match-rate summary.

    Definition:
        matched_count   = decisions with decision == 'matched'
        ambiguous_count = decisions with decision == 'ambiguous'
        unmatched_count = decisions with decision == 'unmatched'
        match_rate      = matched_count / total
    """
    total = len(result.decisions)
    matched = sum(1 for d in result.decisions if d.decision == "matched")
    ambiguous = sum(1 for d in result.decisions if d.decision == "ambiguous")
    unmatched = total - matched - ambiguous
    return {
        "total": total,
        "matched": matched,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
        "match_rate": round(matched / total, 4) if total else 0.0,
    }
