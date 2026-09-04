import csv
import copy
import subprocess
from datetime import date
from decimal import Decimal
import pytest

from app.models.canonical import CanonicalTransaction, ReconciliationDecision, ExceptionRecord, AuditRecord
from app.services.reconciliation import FinalReconciliationResult, reconcile
from app.services.schema_mapper import SchemaMapper, MockLLMProvider
from app.services.normalizer import Normalizer
from app.services.qa import (
    FinanceQA,
    QuestionInterpreter,
    DeterministicRetriever,
    FactComputer,
    AnswerGenerator,
)
from app.models.qa import IntentDefinition, GroundedFactSet, GroundedAnswer


def _rzp(record_id="rzp_001", amount="1000.00", ref=None,
         dt=date(2026, 9, 1), gross=None, fee=None, tax=None,
         settlement_id=None, transaction_type="payment"):
    return CanonicalTransaction(
        record_id=record_id, source="razorpay",
        transaction_type=transaction_type,
        amount=Decimal(amount) if amount else None,
        gross_amount=Decimal(gross) if gross else None,
        fee=Decimal(fee) if fee else None,
        tax=Decimal(tax) if tax else None,
        reference=ref,
        settlement_id=settlement_id or record_id,
        settlement_date=dt,
    )


def _bank(record_id="bank_001", amount="1000.00", ref=None, dt=date(2026, 9, 1)):
    return CanonicalTransaction(
        record_id=record_id, source="bank",
        transaction_type="unknown",
        amount=Decimal(amount) if amount else None,
        reference=ref, posted_date=dt,
    )


class TestQuestionInterpreter:

    def test_intent_parsing(self):
        cmd = QuestionInterpreter.parse("How many transactions were matched?")
        assert cmd.intent == IntentDefinition.RESOLUTION_SUMMARY

        cmd = QuestionInterpreter.parse("Show unresolved transactions.")
        assert cmd.intent == IntentDefinition.UNRESOLVED_RECORDS

        cmd = QuestionInterpreter.parse("Why wasn't razorpay_17 reconciled?")
        assert cmd.intent == IntentDefinition.TRANSACTION_EXPLANATION
        assert cmd.record_id == "razorpay_17"

        cmd = QuestionInterpreter.parse("How much was settled on September 1?")
        assert cmd.intent == IntentDefinition.SETTLEMENT_TOTAL
        assert cmd.date == "September 1"

        cmd = QuestionInterpreter.parse("How much was deducted in fees?")
        assert cmd.intent == IntentDefinition.FEE_TOTAL

        cmd = QuestionInterpreter.parse("How much GST was charged?")
        assert cmd.intent == IntentDefinition.TAX_TOTAL

        cmd = QuestionInterpreter.parse("Show refunds.")
        assert cmd.intent == IntentDefinition.REFUNDS

        cmd = QuestionInterpreter.parse("Which settlements were batched?")
        assert cmd.intent == IntentDefinition.BATCH_SETTLEMENTS

        cmd = QuestionInterpreter.parse("What is the status of UTR839201?")
        assert cmd.intent == IntentDefinition.REFERENCE_LOOKUP
        assert cmd.reference == "UTR839201"

        cmd = QuestionInterpreter.parse("Did customer X receive cash?")
        assert cmd.intent == IntentDefinition.UNSUPPORTED


class TestDeterministicCalculationsAndRetrieval:

    def test_settlement_total_calculation(self):
        s1 = _rzp(record_id="s1", amount="4000.00", dt=date(2026, 9, 1))
        s2 = _rzp(record_id="s2", amount="5787.60", dt=date(2026, 9, 1))
        b1 = _bank(record_id="b1", amount="4000.00", dt=date(2026, 9, 1))
        b2 = _bank(record_id="b2", amount="5787.60", dt=date(2026, 9, 1))

        res = reconcile([s1, s2], [b1, b2])
        qa = FinanceQA(res, [s1, s2])
        ans = qa.ask("How much was settled on September 1?")

        assert "s1" in ans.evidence.get("record_ids", [])
        assert "s2" in ans.evidence.get("record_ids", [])
        assert ans.evidence.get("facts", {}).get("total_settlement") == 9787.60

    def test_fee_and_tax_totals(self):
        s1 = _rzp(record_id="s1", amount="9787.60", gross="10000", fee="180", tax="32.40")
        s2 = _rzp(record_id="s2", amount="4900.00", gross="5000", fee="84.75", tax="15.25")
        res = reconcile([s1, s2], [])
        qa = FinanceQA(res, [s1, s2])

        fee_ans = qa.ask("How much was deducted in fees?")
        assert fee_ans.evidence.get("facts", {}).get("total_fee") == 264.75

        tax_ans = qa.ask("How much tax deducted?")
        assert tax_ans.evidence.get("facts", {}).get("total_tax") == 47.65


class TestHallucinationBoundary:

    def test_accepted_when_facts_match(self):
        facts = GroundedFactSet(
            question="What was settled on September 1?",
            intent=IntentDefinition.SETTLEMENT_TOTAL,
            record_ids=["razorpay_17"],
            numerical_values=[9787.60],
            facts={"total_settlement": 9787.60}
        )
        generator = AnswerGenerator(lambda f: "The settlement total was 9,787.60 for razorpay_17.")
        ans = generator.generate(facts)
        assert not ans.evidence.get("hallucination_rejected")
        assert ans.answer == "The settlement total was 9,787.60 for razorpay_17."

    def test_rejected_when_amount_hallucinated(self):
        facts = GroundedFactSet(
            question="What was settled on September 1?",
            intent=IntentDefinition.SETTLEMENT_TOTAL,
            record_ids=["razorpay_17"],
            numerical_values=[9787.60],
            facts={"total_settlement": 9787.60}
        )
        generator = AnswerGenerator(lambda f: "The settlement total was 99787.60 for razorpay_17.")
        ans = generator.generate(facts)
        # Key: hallucination was detected and rejected
        assert ans.evidence.get("hallucination_rejected")
        # When hallucinated answer is rejected, fallback (deterministic) answer is used instead
        assert len(ans.answer) > 0

    def test_rejected_when_record_id_hallucinated(self):
        facts = GroundedFactSet(
            question="What was settled on September 1?",
            intent=IntentDefinition.SETTLEMENT_TOTAL,
            record_ids=["razorpay_17"],
            numerical_values=[9787.60],
            facts={"total_settlement": 9787.60}
        )
        generator = AnswerGenerator(lambda f: "The settlement total was 9787.60 for razorpay_999.")
        ans = generator.generate(facts)
        # Key: hallucination was detected and rejected
        assert ans.evidence.get("hallucination_rejected")
        # When hallucinated answer is rejected, fallback (deterministic) answer is used instead
        assert len(ans.answer) > 0


class TestGroundedRefusalAndUnsupported:

    def test_unsupported_question_refusal(self):
        res = reconcile([], [])
        qa = FinanceQA(res, [])
        ans = qa.ask("Did customer X receive cash?")
        # Answer should be unsupported or couldn't find enough information
        assert "not able to answer" in ans.answer.lower() or "couldn't find enough" in ans.answer.lower()

    def test_missing_record_explanation_refusal(self):
        res = reconcile([], [])
        qa = FinanceQA(res, [])
        ans = qa.ask("Why wasn't razorpay_999 reconciled?")
        # Answer should indicate insufficient information
        assert "couldn't find enough" in ans.answer.lower() or "please try" in ans.answer.lower()


class TestImmutableState:

    def test_qa_does_not_mutate_reconciliation_result(self):
        s1 = _rzp(record_id="s1", ref="UTR100")
        b1 = _bank(record_id="b1", ref="UTR100")
        res = reconcile([s1], [b1])

        snap_decisions = copy.deepcopy(res.decisions)
        snap_exceptions = copy.deepcopy(res.exceptions)
        snap_audits = copy.deepcopy(res.audit_records)

        qa = FinanceQA(res, [s1])
        qa.ask("How many transactions were matched?")
        qa.ask("Why wasn't s1 reconciled?")
        qa.ask("How much was settled on September 1?")

        assert res.decisions == snap_decisions
        assert res.exceptions == snap_exceptions
        assert res.audit_records == snap_audits


class TestRealDatasetQA:

    @pytest.fixture(autouse=True, scope="class")
    def generate_data(self):
        subprocess.run(["python3", "scripts/generate_data.py"], check=True, capture_output=True)

    def _load(self):
        mapper = SchemaMapper(MockLLMProvider())
        norm = Normalizer()
        def load(path, source):
            with open(path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                cols = reader.fieldnames
            mapping = mapper.map_source(source, cols, [])
            return norm.normalize(rows, mapping)
        rzp = load("data/raw/razorpay_settlements.csv", "razorpay")
        bank = load("data/raw/bank_statement.csv", "bank")
        return rzp, bank

    def test_representative_questions_on_real_data(self):
        rzp, bank = self._load()
        res = reconcile(rzp, bank)
        qa = FinanceQA(res, rzp)

        # 1. Resolution summary
        ans1 = qa.ask("How many transactions were matched?")
        assert ans1.evidence.get("facts", {}).get("total_source_records") == len(rzp)

        # 2. Unresolved transactions
        ans2 = qa.ask("Show unresolved transactions.")
        assert len(ans2.evidence.get("record_ids", [])) > 0

        # 3. Transaction explanation
        ambiguous_id = ans2.evidence.get("record_ids")[0]
        ans3 = qa.ask(f"Why wasn't {ambiguous_id} reconciled?")
        assert ambiguous_id in ans3.evidence.get("record_ids", [])

        # 4. Fee & tax totals
        ans4 = qa.ask("How much was deducted in fees?")
        assert ans4.evidence.get("facts", {}).get("total_fee") > 0

        # 5. Refunds
        ans5 = qa.ask("Show refunds.")
        assert "record_ids" in ans5.evidence

        # 6. Batched settlements
        ans6 = qa.ask("Which settlements were batched?")
        assert "record_ids" in ans6.evidence
