import re
from typing import Any, List, Optional
from decimal import Decimal

from app.models.canonical import CanonicalTransaction, ReconciliationDecision, ExceptionRecord, AuditRecord
from app.services.reconciliation import FinalReconciliationResult
from app.services.report import generate_reconciliation_report
from app.models.qa import IntentDefinition, ParsedCommand, GroundedFactSet, GroundedAnswer


class QuestionInterpreter:
    """Deterministically interprets user questions based on keywords and regex."""

    @staticmethod
    def parse(question: str) -> ParsedCommand:
        q = question.lower()
        
        # 1. Reference Lookup
        # looking for UTR or anything resembling a reference
        ref_match = re.search(r"reference (utr\d+|[\w\d]+)|utr\d+", q)
        if "status of" in q or "reference" in q or "utr" in q:
            ref = None
            if ref_match:
                ref = ref_match.group(1) if ref_match.group(1) else ref_match.group(0)
                # Cleanup if user says "status of UTR839201"
                ref = ref.split()[-1].upper()
            return ParsedCommand(intent=IntentDefinition.REFERENCE_LOOKUP, reference=ref)

        # 2. Transaction Explanation
        tx_match = re.search(r"(razorpay_\d+|set_\d+|txn_\d+|bank_\d+)", q)
        if "why wasn't" in q or "why is" in q or "explain" in q or tx_match:
            record_id = tx_match.group(1) if tx_match else None
            # If fee/tax keywords are present and it's asking 'why is this settlement short' 
            # without a specific ID, we might need a general search or we fall back to unsupported.
            if "short" in q and not record_id:
                pass # Can't explain without an ID, unless we expect the frontend to pass context.
            else:
                return ParsedCommand(intent=IntentDefinition.TRANSACTION_EXPLANATION, record_id=record_id)
        
        # 3. Resolution Summary
        if ("match rate" in q or "how many transactions were matched" in q
                or "how many were matched" in q or "how many required llm" in q
                or ("matched" in q and ("how many" in q or "count" in q))):
            return ParsedCommand(intent=IntentDefinition.RESOLUTION_SUMMARY)
            
        # 4. Unresolved Records
        if any(phrase in q for phrase in (
            "unresolved", "unmatched", "not reconciled", "pending review",
            "open exception", "exceptions", "failed to match",
        )):
            return ParsedCommand(intent=IntentDefinition.UNRESOLVED_RECORDS)
        if "ambiguous" in q:
            return ParsedCommand(intent=IntentDefinition.UNRESOLVED_RECORDS)
        # 5. Settlement Total
        date_match = re.search(r"on (january|february|march|april|may|june|july|august|september|october|november|december)\ \d+", q)
        if ("how much was settled" in q or "settlement amount" in q
                or "total settled" in q or "settled amount" in q
                or "which settlements occurred" in q):
            dt_str = date_match.group(0).replace("on ", "").strip().title() if date_match else None
            return ParsedCommand(intent=IntentDefinition.SETTLEMENT_TOTAL, date=dt_str)
            
        # 6. Fee Total
        if ("fee" in q or "fees" in q) and ("gst" in q or "tax" in q):
            return ParsedCommand(intent=IntentDefinition.FEE_AND_TAX_TOTAL)
        if "deducted in fees" in q or "how much fee" in q or "total fee" in q or "fees deducted" in q:
            return ParsedCommand(intent=IntentDefinition.FEE_TOTAL)
            
        # 7. Tax Total
        if "gst was charged" in q or "how much tax" in q or "tax deducted" in q:
            return ParsedCommand(intent=IntentDefinition.TAX_TOTAL)
            
        # 8. Refunds
        if "refund" in q:
            return ParsedCommand(intent=IntentDefinition.REFUNDS)
            
        # 9. Batch Settlements
        if "batched" in q or "make up this bank settlement" in q:
            return ParsedCommand(intent=IntentDefinition.BATCH_SETTLEMENTS)
            
        return ParsedCommand(intent=IntentDefinition.UNSUPPORTED)


class DeterministicRetriever:
    """Retrieves exact records based on ParsedCommand."""

    def __init__(self, result: FinalReconciliationResult, source_records: List[CanonicalTransaction]):
        self.result = result
        self.source_records = source_records
        self.src_map = {r.record_id: r for r in source_records}
    
    def retrieve_by_id(self, record_id: str) -> Optional[CanonicalTransaction]:
        return self.src_map.get(record_id)

    def retrieve_decision(self, record_id: str) -> Optional[ReconciliationDecision]:
        for d in self.result.decisions:
            if d.source_record_id == record_id or d.candidate_record_id == record_id:
                return d
        return None

    def retrieve_exceptions(self, record_id: str) -> List[ExceptionRecord]:
        return [e for e in self.result.exceptions if e.record_id == record_id]
        
    def retrieve_audits(self, record_id: str) -> List[AuditRecord]:
        return [a for a in self.result.audit_records if a.record_id == record_id]

    def filter_by_date(self, date_str: str) -> List[CanonicalTransaction]:
        # Minimal string approximation for "September 1" -> "2026-09-01"
        # We assume 2026 as per dataset. In a real system, date parsing would be robust.
        # Here we just do a simplistic check for the Buildathon format.
        matches = []
        # Normalizer converted dates to date objects. Let's do a loose string match on formatting
        if not date_str:
            return matches
        ds = date_str.lower()
        month_map = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
        parts = ds.split()
        if len(parts) == 2 and parts[0] in month_map:
            month = month_map[parts[0]]
            day = int(parts[1])
            target_date = f"2026-{month:02d}-{day:02d}"
            
            for src in self.source_records:
                if src.settlement_date and str(src.settlement_date) == target_date:
                    matches.append(src)
        return matches

    def retrieve_unresolved(self) -> List[ReconciliationDecision]:
        return [d for d in self.result.decisions if d.decision in ("ambiguous", "unmatched")]
        
    def retrieve_refunds(self) -> List[ReconciliationDecision]:
        return [d for d in self.result.decisions if "refund" in d.method or "refund" in str(d.evidence)]
        
    def retrieve_batches(self) -> List[ReconciliationDecision]:
        return [d for d in self.result.decisions if "batch" in d.method]

    def retrieve_by_reference(self, ref: str) -> List[CanonicalTransaction]:
        matches = []
        if not ref:
            return matches
        r = ref.lower()
        for src in self.source_records:
            if src.reference and r in src.reference.lower():
                matches.append(src)
        return matches


class FactComputer:
    """Computes verified facts from deterministically retrieved records."""

    def __init__(self, result: FinalReconciliationResult, retriever: DeterministicRetriever):
        self.result = result
        self.retriever = retriever

    def compute(self, question: str, cmd: ParsedCommand) -> GroundedFactSet:
        fact_set = GroundedFactSet(question=question, intent=cmd.intent)
        
        if cmd.intent == IntentDefinition.RESOLUTION_SUMMARY:
            report = generate_reconciliation_report(self.result)
            fact_set.facts = {
                "total_source_records": report.total_source_records,
                "deterministic_matches": report.deterministic_matches,
                "llm_resolved_matches": report.llm_resolved_matches,
                "ambiguous_records": report.ambiguous_records,
                "unmatched_records": report.unmatched_records,
                "overall_resolution_rate": report.overall_resolution_rate,
                "unresolved_rate": report.unresolved_rate
            }
            fact_set.numerical_values = [
                report.total_source_records, report.deterministic_matches, 
                report.llm_resolved_matches, report.ambiguous_records, 
                report.unmatched_records, report.overall_resolution_rate, report.unresolved_rate
            ]
            return fact_set

        if cmd.intent == IntentDefinition.UNRESOLVED_RECORDS:
            unresolved = self.retriever.retrieve_unresolved()
            fact_set.record_ids = [d.source_record_id for d in unresolved]
            fact_set.facts = {
                "count": len(unresolved),
                "ambiguous": [d.source_record_id for d in unresolved if d.decision == "ambiguous"],
                "unmatched": [d.source_record_id for d in unresolved if d.decision == "unmatched"]
            }
            fact_set.numerical_values = [len(unresolved)]
            return fact_set
            
        if cmd.intent == IntentDefinition.TRANSACTION_EXPLANATION:
            if not cmd.record_id:
                fact_set.insufficient_evidence = True
                return fact_set
                
            dec = self.retriever.retrieve_decision(cmd.record_id)
            if not dec:
                fact_set.insufficient_evidence = True
                return fact_set
                
            excs = self.retriever.retrieve_exceptions(cmd.record_id)
            fact_set.record_ids = [cmd.record_id]
            if dec.candidate_record_id:
                fact_set.record_ids.append(dec.candidate_record_id)
            if "candidate_record_ids" in dec.evidence:
                fact_set.record_ids.extend(dec.evidence["candidate_record_ids"])
                
            fact_set.facts = {
                "decision": dec.decision,
                "method": dec.method,
                "reason": dec.reason,
                "evidence": dec.evidence,
                "exceptions": [e.category for e in excs]
            }
            # We can also add computations like expected amount if gross/fee/tax exists.
            src = self.retriever.retrieve_by_id(cmd.record_id)
            if src and src.gross_amount and src.fee is not None and src.tax is not None:
                expected = src.gross_amount - src.fee - src.tax
                fact_set.facts["expected_amount"] = float(expected)
                fact_set.numerical_values.extend([float(src.gross_amount), float(src.fee), float(src.tax), float(expected)])

            return fact_set
            
        if cmd.intent == IntentDefinition.SETTLEMENT_TOTAL:
            recs = self.retriever.filter_by_date(cmd.date) if cmd.date else self.retriever.source_records
            if not recs:
                fact_set.insufficient_evidence = True
                return fact_set
                
            total = sum((r.amount for r in recs if r.amount is not None), Decimal('0'))
            fact_set.record_ids = [r.record_id for r in recs]
            fact_set.facts = {
                "date": cmd.date or "the full dataset",
                "count": len(recs),
                "total_settlement": float(total)
            }
            fact_set.numerical_values = [len(recs), float(total)]
            return fact_set

        if cmd.intent == IntentDefinition.FEE_TOTAL:
            # We total fees across all retrieved records
            recs = self.retriever.source_records
            total = sum((r.fee for r in recs if r.fee is not None), Decimal('0'))
            fact_set.facts = {"total_fee": float(total)}
            fact_set.numerical_values = [float(total)]
            return fact_set

        if cmd.intent == IntentDefinition.TAX_TOTAL:
            recs = self.retriever.source_records
            total = sum((r.tax for r in recs if r.tax is not None), Decimal('0'))
            fact_set.facts = {"total_tax": float(total)}
            fact_set.numerical_values = [float(total)]
            return fact_set

        if cmd.intent == IntentDefinition.FEE_AND_TAX_TOTAL:
            recs = self.retriever.source_records
            total_fee = sum((r.fee for r in recs if r.fee is not None), Decimal('0'))
            total_tax = sum((r.tax for r in recs if r.tax is not None), Decimal('0'))
            fact_set.facts = {"total_fee": float(total_fee), "total_tax": float(total_tax)}
            fact_set.numerical_values = [float(total_fee), float(total_tax)]
            return fact_set

        if cmd.intent == IntentDefinition.REFUNDS:
            refs = self.retriever.retrieve_refunds()
            fact_set.record_ids = [d.source_record_id for d in refs]
            fact_set.facts = {"count": len(refs)}
            fact_set.numerical_values = [len(refs)]
            return fact_set
            
        if cmd.intent == IntentDefinition.BATCH_SETTLEMENTS:
            batches = self.retriever.retrieve_batches()
            for b in batches:
                if "source_record_ids" in b.evidence:
                    fact_set.record_ids.extend(b.evidence["source_record_ids"])
                if "target_record_id" in b.evidence:
                    fact_set.record_ids.append(b.evidence["target_record_id"])
            
            fact_set.facts = {"batch_decisions_count": len(batches)}
            fact_set.numerical_values = [len(batches)]
            return fact_set
            
        if cmd.intent == IntentDefinition.REFERENCE_LOOKUP:
            if not cmd.reference:
                fact_set.insufficient_evidence = True
                return fact_set
                
            matches = self.retriever.retrieve_by_reference(cmd.reference)
            if not matches:
                fact_set.insufficient_evidence = True
                return fact_set
                
            fact_set.record_ids = [m.record_id for m in matches]
            # Get decisions for these
            decs = [self.retriever.retrieve_decision(m.record_id) for m in matches]
            decs = [d for d in decs if d]
            fact_set.facts = {
                "reference": cmd.reference,
                "matches_count": len(matches),
                "statuses": [d.decision for d in decs]
            }
            fact_set.numerical_values = [len(matches)]
            return fact_set

        if cmd.intent == IntentDefinition.UNSUPPORTED:
            fact_set.insufficient_evidence = True
            return fact_set

        return fact_set


class AnswerGenerator:
    """Generates an answer using an abstraction, checking for hallucinations."""

    def __init__(self, provider_func=None):
        # provider_func takes GroundedFactSet (as dict/str) and returns a raw string
        self.provider_func = provider_func

    def _generate_fallback_answer(self, fact_set: GroundedFactSet) -> str:
        """Generate human-friendly fallback answers based on intent and facts."""
        intent = fact_set.intent
        facts = fact_set.facts
        
        if intent == IntentDefinition.RESOLUTION_SUMMARY:
            total = facts.get("total_source_records", 0)
            det_matches = facts.get("deterministic_matches", 0)
            llm_matches = facts.get("llm_resolved_matches", 0)
            ambiguous = facts.get("ambiguous_records", 0)
            unmatched = facts.get("unmatched_records", 0)
            rate = facts.get("overall_resolution_rate", 0)
            
            return (
                f"Out of {total} source transactions, {det_matches} were matched using deterministic rules "
                f"and {llm_matches} were resolved by arbitration. "
                f"This gives us an overall resolution rate of {rate:.1f}%. "
                f"There are {ambiguous} ambiguous records and {unmatched} unmatched records still pending review."
            )
        
        elif intent == IntentDefinition.UNRESOLVED_RECORDS:
            count = facts.get("count", 0)
            ambiguous_ids = facts.get("ambiguous", [])
            unmatched_ids = facts.get("unmatched", [])
            
            response = f"There are {count} unresolved records in total. "
            if ambiguous_ids:
                response += f"{len(ambiguous_ids)} are ambiguous and need manual review. "
            if unmatched_ids:
                response += f"{len(unmatched_ids)} are completely unmatched and not found in the bank statement."
            return response.strip()
        
        elif intent == IntentDefinition.TRANSACTION_EXPLANATION:
            decision = facts.get("decision", "unknown")
            method = facts.get("method", "unknown")
            reason = facts.get("reason", "No reason provided")
            
            return (
                f"This transaction was {decision} using the '{method}' method. "
                f"The reasoning: {reason}"
            )
        
        elif intent == IntentDefinition.SETTLEMENT_TOTAL:
            date = facts.get("date", "unknown date")
            count = facts.get("count", 0)
            total = facts.get("total_settlement", 0)
            
            if count == 0:
                return f"No settlements were found for {date}."
            return f"On {date}, {count} settlement(s) totaling ₹{total:,.2f} were processed."
        
        elif intent == IntentDefinition.FEE_TOTAL:
            total_fee = facts.get("total_fee", 0)
            return f"The total fees deducted across all transactions is ₹{total_fee:,.2f}."
        
        elif intent == IntentDefinition.TAX_TOTAL:
            total_tax = facts.get("total_tax", 0)
            return f"The total GST/tax charged across all transactions is ₹{total_tax:,.2f}."
        
        elif intent == IntentDefinition.FEE_AND_TAX_TOTAL:
            return (
                f"Total processing fees are ₹{facts.get('total_fee', 0):,.2f} and "
                f"GST/tax is ₹{facts.get('total_tax', 0):,.2f}."
            )
        
        elif intent == IntentDefinition.REFUNDS:
            count = facts.get("count", 0)
            if count == 0:
                return "No refunds were found in the reconciliation data."
            return f"There are {count} refund(s) in the dataset that have been identified and tracked."
        
        elif intent == IntentDefinition.BATCH_SETTLEMENTS:
            batch_count = facts.get("batch_decisions_count", 0)
            if batch_count == 0:
                return "No batch settlements were found in this reconciliation."
            return f"There are {batch_count} batch settlement(s) where multiple source records were matched against a single bank credit."
        
        elif intent == IntentDefinition.REFERENCE_LOOKUP:
            reference = facts.get("reference", "unknown")
            matches_count = facts.get("matches_count", 0)
            statuses = facts.get("statuses", [])
            
            if matches_count == 0:
                return f"No transactions found with reference '{reference}'."
            
            status_summary = ", ".join(statuses) if statuses else "unknown"
            return f"Found {matches_count} transaction(s) matching reference '{reference}'. Status: {status_summary}."
        
        else:
            return "I'm not able to answer that question. Please try asking about resolution rate, unmatched records, specific transactions, settlement totals, fees, taxes, refunds, or batch settlements."

    def generate(self, fact_set: GroundedFactSet) -> GroundedAnswer:
        if fact_set.insufficient_evidence:
            return GroundedAnswer(
                answer="I couldn't find enough information in the reconciled records to answer that. Please try a different question.",
                evidence={}
            )

        # Generate fallback answer for when LLM is not available
        fallback_answer = self._generate_fallback_answer(fact_set)

        if not self.provider_func:
            return GroundedAnswer(answer=fallback_answer, evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts})

        # Ask provider
        try:
            raw_answer = self.provider_func(fact_set.model_dump())
        except Exception:
            return GroundedAnswer(answer=fallback_answer, evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts})

        if not raw_answer:
            return GroundedAnswer(answer=fallback_answer, evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts})

        # ----------------------------------------------------
        # Hallucination Checker (Deterministic Boundary)
        # ----------------------------------------------------
        
        # 1. Check numbers: any number (digits with optional decimal) in the text must exist in facts
        # We extract numbers, allowing commas. We'll strip commas for parsing.
        numbers_in_text = re.findall(r'\b\d+(?:,\d{3})*(?:\.\d+)?\b', raw_answer)
        valid_numbers = [float(n) for n in fact_set.numerical_values]
        
        for num_str in numbers_in_text:
            # ignore IDs that look like pure numbers but match known IDs if applicable, or small integers that might be dates
            val = float(num_str.replace(",", ""))
            # Loose heuristic: if a number is not in valid_numbers, and it's large (e.g. monetary), fallback. 
            # We don't want to fail if the LLM says "There are 2 candidates" and 2 wasn't explicitly in numerical_values
            # but is implied. Thus, we check strictly against floats > 1000 or detailed decimals unless it's in the list.
            if val not in valid_numbers and (val > 100 or "." in num_str):
                # Check if it might be part of an ID (e.g. '17' in 'razorpay_17')
                part_of_id = False
                for rid in fact_set.record_ids:
                    if str(val).rstrip("0").rstrip(".") in rid or num_str in rid:
                        part_of_id = True
                        break
                # Only reject if certainly ungrounded monetary/id value
                if not part_of_id:
                    return GroundedAnswer(
                        answer=fallback_answer, 
                        evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts, "hallucination_rejected": True}
                    )

        # 2. Check IDs: Look for patterns razorpay_, bank_, set_, txn_
        id_matches = re.findall(r"\b(razorpay_\w+|bank_\w+|set_\w+|txn_\w+|inv_\w+)\b", raw_answer)
        for cand_id in id_matches:
            if cand_id not in fact_set.record_ids:
                return GroundedAnswer(
                    answer=fallback_answer, 
                    evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts, "hallucination_rejected": True}
                )

        # Passed checks
        return GroundedAnswer(answer=raw_answer, evidence={"record_ids": fact_set.record_ids, "facts": fact_set.facts})


class FinanceQA:
    """The facade for Milestone 7 Q&A process."""

    def __init__(self, result: FinalReconciliationResult, source_records: List[CanonicalTransaction], provider_func=None):
        self.interpreter = QuestionInterpreter()
        self.retriever = DeterministicRetriever(result, source_records)
        self.fact_computer = FactComputer(result, self.retriever)
        self.generator = AnswerGenerator(provider_func)

    def ask(self, question: str) -> GroundedAnswer:
        cmd = self.interpreter.parse(question)
        fact_set = self.fact_computer.compute(question, cmd)
        answer = self.generator.generate(fact_set)
        return answer
