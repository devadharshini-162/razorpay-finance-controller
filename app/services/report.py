"""
Match-Rate Reporting — Milestone 6

Read-only reporting layer that consumes a FinalReconciliationResult and
produces structured, traceable, explainable reconciliation metrics.

All calculations are deterministic Python — no LLM, no ground truth, no I/O.

Denominator
-----------
The primary denominator is **total Razorpay source records entering
reconciliation**, i.e. `len(result.decisions)`.  Every Razorpay source record
produces exactly one ReconciliationDecision.  Bank-only records that have no
corresponding Razorpay record are NOT included in this denominator.

Method discrimination
---------------------
A final ``decision == "matched"`` record is classified as:

* **deterministic** if ``method != "llm_arbitration"``
* **llm_resolved**  if ``method == "llm_arbitration"``

This avoids hardcoding an exhaustive list of deterministic methods and is
future-proof if new deterministic rules are added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.canonical import ExceptionRecord, ReconciliationDecision
from app.services.reconciliation import FinalReconciliationResult

LLM_METHOD = "llm_arbitration"


# ---------------------------------------------------------------------------
# Metric model
# ---------------------------------------------------------------------------

@dataclass
class ReconciliationReport:
    """Structured reconciliation metrics — every number traceable to record IDs."""

    # ---- primary counts ---------------------------------------------------
    total_source_records: int = 0

    deterministic_matches: int = 0
    llm_resolved_matches: int = 0
    ambiguous_records: int = 0
    unmatched_records: int = 0

    # ---- derived -----------------------------------------------------------
    overall_resolved_records: int = 0
    overall_resolution_rate: float = 0.0   # percentage 0–100
    unresolved_rate: float = 0.0           # percentage 0–100

    # ---- traceability (record IDs) -----------------------------------------
    deterministic_match_ids: list[str] = field(default_factory=list)
    llm_resolved_ids: list[str] = field(default_factory=list)
    ambiguous_ids: list[str] = field(default_factory=list)
    unmatched_ids: list[str] = field(default_factory=list)

    # ---- method breakdown --------------------------------------------------
    deterministic_method_breakdown: dict[str, int] = field(default_factory=dict)

    # ---- exception summary -------------------------------------------------
    total_exceptions: int = 0
    active_exceptions: int = 0
    resolved_exceptions: int = 0
    exceptions_by_category: dict[str, int] = field(default_factory=dict)
    high_severity_exceptions: int = 0

    def summary(self) -> str:
        """Human-readable reconciliation summary."""
        lines = [
            "",
            "═══════════════════════════════════════════",
            "        Reconciliation Summary",
            "═══════════════════════════════════════════",
            "",
            f"  Total Razorpay records:   {self.total_source_records}",
            "",
            f"  Deterministic matches:    {self.deterministic_matches}",
        ]
        # Method breakdown
        for method, count in sorted(self.deterministic_method_breakdown.items()):
            lines.append(f"    ├─ {method}: {count}")
        lines += [
            f"  LLM-resolved:             {self.llm_resolved_matches}",
            f"  Still ambiguous:          {self.ambiguous_records}",
            f"  Unmatched:                {self.unmatched_records}",
            "",
            f"  Overall resolution rate:  {self.overall_resolution_rate:.1f}%",
            f"  Unresolved rate:          {self.unresolved_rate:.1f}%",
            "",
            "───────────────────────────────────────────",
            f"  Total exceptions:         {self.total_exceptions}",
            f"    Active (unresolved):    {self.active_exceptions}",
            f"    Resolved by LLM:       {self.resolved_exceptions}",
            f"    High severity:         {self.high_severity_exceptions}",
        ]
        if self.exceptions_by_category:
            lines.append("")
            lines.append("  Exception categories:")
            for cat, count in sorted(self.exceptions_by_category.items()):
                lines.append(f"    ├─ {cat}: {count}")
        lines += [
            "",
            "═══════════════════════════════════════════",
            "",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report generator (read-only — does NOT mutate the result)
# ---------------------------------------------------------------------------

def generate_reconciliation_report(
    result: FinalReconciliationResult,
) -> ReconciliationReport:
    """Compute reconciliation metrics from a FinalReconciliationResult.

    This function is entirely read-only.  It never mutates decisions,
    exceptions, or audit records.
    """
    report = ReconciliationReport()

    decisions: list[ReconciliationDecision] = result.decisions
    exceptions: list[ExceptionRecord] = result.exceptions

    # ------------------------------------------------------------------
    # Primary denominator
    # ------------------------------------------------------------------
    report.total_source_records = len(decisions)

    if report.total_source_records == 0:
        return report

    # ------------------------------------------------------------------
    # Classify each decision
    # ------------------------------------------------------------------
    method_counts: dict[str, int] = {}

    for d in decisions:
        if d.decision == "matched":
            if d.method == LLM_METHOD:
                report.llm_resolved_matches += 1
                report.llm_resolved_ids.append(d.source_record_id)
            else:
                report.deterministic_matches += 1
                report.deterministic_match_ids.append(d.source_record_id)
                method_counts[d.method] = method_counts.get(d.method, 0) + 1
        elif d.decision == "ambiguous":
            report.ambiguous_records += 1
            report.ambiguous_ids.append(d.source_record_id)
        elif d.decision == "unmatched":
            report.unmatched_records += 1
            report.unmatched_ids.append(d.source_record_id)

    report.deterministic_method_breakdown = method_counts

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------
    report.overall_resolved_records = (
        report.deterministic_matches + report.llm_resolved_matches
    )
    report.overall_resolution_rate = round(
        (report.overall_resolved_records / report.total_source_records) * 100, 2
    )
    report.unresolved_rate = round(
        100.0 - report.overall_resolution_rate, 2
    )

    # ------------------------------------------------------------------
    # Exception summary
    # ------------------------------------------------------------------
    report.total_exceptions = len(exceptions)
    for exc in exceptions:
        cat = exc.category
        report.exceptions_by_category[cat] = (
            report.exceptions_by_category.get(cat, 0) + 1
        )
        if exc.severity == "high":
            report.high_severity_exceptions += 1

        # Distinguish active vs resolved using existing evidence
        if exc.evidence.get("resolved_by"):
            report.resolved_exceptions += 1
        else:
            report.active_exceptions += 1

    return report
