import os
import json
import traceback
from typing import List, Dict, Any, Type, Optional, Literal
from pydantic import BaseModel, Field, model_validator

from app.services.schema_mapper import LLMProvider
from app.services.arbitration_provider import ArbitrationProvider
from app.models.mapping import MappingResult
from app.services.arbitrator import LLMArbitrationDecision
from app.models.canonical import CanonicalTransaction
from app.models.qa import GroundedFactSet

try:
    import google.generativeai as genai
except ImportError:
    genai = None

GEMINI_MODEL_DEFAULT = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "5"))


class GeminiBatchArbitrationDecision(BaseModel):
    """Wire contract for one item in Gemini's batch response.

    Keeping evidence as one short string makes the JSON contract reliable for
    hosted models. The application converts it into structured audit evidence.
    """

    source_record_id: str
    decision: Literal["matched", "ambiguous"]
    candidate_record_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=240)
    evidence: str = Field(default="")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_choice(self):
        if self.decision == "matched" and not self.candidate_record_id:
            raise ValueError("A matched decision requires candidate_record_id.")
        if self.decision == "ambiguous" and self.candidate_record_id:
            raise ValueError("An ambiguous decision must not select a candidate.")
        return self


class GeminiBatchArbitrationResponse(BaseModel):
    decisions: list[GeminiBatchArbitrationDecision] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

class GeminiProviderMixin:
    """Shared mixin for Gemini-based providers."""

    def __init__(self, model_name: str = GEMINI_MODEL_DEFAULT):
        if not genai:
            raise ImportError("google-generativeai package is not installed.")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        genai.configure(api_key=api_key)
        self.model_name = model_name
        self._available = True

    def _generate_structured_json(self, prompt: str, schema_class: Type) -> dict:
        """Call Gemini demanding structured JSON output that conforms to a Pydantic schema."""
        if not self._available:
            raise RuntimeError("Gemini is temporarily unavailable for this reconciliation run.")
        model = genai.GenerativeModel(self.model_name)

        try:
            # We enforce application/json natively.
            # We do not pass response_schema because Protobuf Schema fails on dynamic dicts (additionalProperties).
            response = model.generate_content(
                f"{prompt}\nReturn JSON strictly matching this schema:\n{json.dumps(schema_class.model_json_schema())}",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0  # Must be purely deterministic translation
                ),
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )
            return json.loads(response.text)
        except Exception as e:
            self._available = False
            # Graceful fallback mechanisms should catch these exceptions in the caller
            raise RuntimeError(f"Gemini API generation failed: {e}\n{traceback.format_exc()}")


class GeminiLLMProvider(LLMProvider, GeminiProviderMixin):
    """Google Gemini implementation for Schema Mapping."""

    def __init__(self, model_name: str = GEMINI_MODEL_DEFAULT):
        GeminiProviderMixin.__init__(self, model_name)

    def map_schema(self, source_name: str, columns: List[str], sample_rows: List[Dict[str, Any]]) -> MappingResult:
        prompt = f"""
You are a financial data schema mapper.
Map the following file columns to the standard canonical names.
Source type: {source_name}
Columns: {columns}
Sample Rows: {sample_rows}

Rules:
1. Map strictly to: record_id, transaction_type, transaction_id, order_id, settlement_id, reference, amount, gross_amount, fee, tax, adjustment, refund_amount, currency, transaction_date, settlement_date, posted_date, counterparty, description, metadata.
2. If a column does not fit, add it to unmapped_columns.
"""
        try:
            result_dict = self._generate_structured_json(prompt, MappingResult)

            # Ensure the structured dict complies with the mapping result return type
            return MappingResult(
                source_name=source_name,
                column_mapping=result_dict.get("column_mapping", {}),
                unmapped_columns=result_dict.get("unmapped_columns", []),
                confidence=result_dict.get("confidence", 0.0),
                explanation=result_dict.get("explanation", ""),
                audit_info={"provider": "GeminiLLMProvider", "model": self.model_name}
            )
        except Exception as e:
            print(f"[GeminiLLMProvider] Falling back due to Error: {e}")
            # If the API fails completely, fallback to empty mapping to gracefully degrade
            return MappingResult(
                source_name=source_name,
                column_mapping={},
                unmapped_columns=columns,
                confidence=0.0,
                explanation=f"Gemini fallback error: {str(e)}",
                audit_info={"provider": "GeminiLLMProvider_Fallback"}
            )


class GeminiArbitrationProvider(ArbitrationProvider, GeminiProviderMixin):
    """Google Gemini implementation for Arbitrating Ambiguous Records."""

    def __init__(self, model_name: str = GEMINI_MODEL_DEFAULT):
        GeminiProviderMixin.__init__(self, model_name)

    def resolve_ambiguity(
        self,
        source_record: CanonicalTransaction,
        candidates: List[CanonicalTransaction],
        deterministic_evidence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Produce a raw dictionary representing the arbitration decision.
        Never invent a candidate ID.
        """
        valid_candidate_ids = [c.record_id for c in candidates]

        prompt = f"""
You are an expert financial reconciler.
Evaluate this Razorpay source record and choose ONE best matching bank candidate, or determine it is truly ambiguous.
Source Record:
{source_record.model_dump_json(exclude_none=True)}

Deterministic Evidence:
{deterministic_evidence}

Candidates:
"""
        for i, cand in enumerate(candidates):
            prompt += f"\n--- Candidate {i+1} ---\n{cand.model_dump_json(exclude_none=True)}"

        prompt += f"""

Decision Rules:
1. "decision" must be exactly "matched" or "ambiguous".
2. "candidate_record_id" MUST strictly be one of: {valid_candidate_ids}. If no single clear match, use null.
3. You must not invent candidate ids or facts.
4. "confidence" must be between 0.0 and 1.0.
"""

        try:
            result_dict = self._generate_structured_json(prompt, LLMArbitrationDecision)

            # Post-validation to enforce strict boundaries
            decision = result_dict.get("decision")
            candidate_id = result_dict.get("candidate_record_id")

            if decision == "matched" and candidate_id not in valid_candidate_ids:
                # Force graceful degradation if hallucinated candidate
                decision = "ambiguous"
                candidate_id = None

            return {
                "decision": decision,
                "candidate_record_id": candidate_id,
                "confidence": result_dict.get("confidence", 0.0),
                "reason": result_dict.get("reason", ""),
                "evidence": {"provider": "GeminiArbitrationProvider", "model": self.model_name}
            }
        except Exception as e:
            print(f"[GeminiArbitrationProvider] Falling back due to Error: {e}")
            return {
                "decision": "ambiguous",
                "candidate_record_id": None,
                "confidence": 0.0,
                "reason": f"API Error: {str(e)}",
                "evidence": {"provider": "GeminiArbitrationProvider_Fallback"}
            }

    def resolve_ambiguities(
        self,
        requests: list[tuple[CanonicalTransaction, list[CanonicalTransaction], dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        """Resolve all ambiguous rows in one bounded Gemini call."""
        if not requests:
            return {}
        cases = []
        for source, candidates, evidence in requests:
            cases.append({
                "source_record_id": source.record_id,
                "source": source.model_dump(mode="json", exclude_none=True),
                "candidate_ids": [candidate.record_id for candidate in candidates],
                "candidates": [candidate.model_dump(mode="json", exclude_none=True) for candidate in candidates],
                "deterministic_evidence": evidence,
            })
        prompt = f"""
You are the final, audit-safe review stage of a financial reconciliation system.
Your goal is NOT to maximize matches. Choose a bank record only when the supplied
evidence makes it clearly more credible than every other candidate. Otherwise,
preserve the ambiguity for human review.

Review every case below independently. Return exactly one decision for every
source_record_id, in the same order. Use only values present in that case.

Required JSON fields for each decision:
- source_record_id: copy exactly from the case
- decision: exactly "matched" or "ambiguous"
- candidate_record_id: a listed candidate ID for matched; null for ambiguous
- confidence: number from 0 to 1
- reason: one plain-English sentence, maximum 180 characters
- evidence: one short plain-English sentence naming the deciding signal, maximum 160 characters

Decision rules:
1. Never invent references, identifiers, amounts, dates, or transaction facts.
2. Do not match merely because amounts or dates are equal when multiple candidates remain.
3. Prefer a unique UTR/reference, a unique exact net amount calculation, or a
   clearly unique date/description signal. If none uniquely separates candidates,
   return ambiguous.
4. Do not add fields, Markdown, explanations outside JSON, arrays inside evidence,
   or a candidate_record_id for an ambiguous decision.

Cases: {json.dumps(cases, default=str)}
"""
        try:
            response = self._generate_structured_json(prompt, GeminiBatchArbitrationResponse)
            by_source = {}
            valid_candidates = {source.record_id: {candidate.record_id for candidate in candidates}
                                for source, candidates, _ in requests}
            for raw_item in response.get("decisions", []):
                item = raw_item.model_dump() if isinstance(raw_item, GeminiBatchArbitrationDecision) else raw_item
                if not isinstance(item, dict):
                    continue
                source_id = item.get("source_record_id")
                if source_id not in valid_candidates:
                    continue
                # source_record_id belongs to the batch envelope, not the
                # strict LLMArbitrationDecision contract. Gemini may also
                # return a concise evidence string; retain it under a stable
                # dictionary key so the downstream validator can accept it.
                decision = {key: value for key, value in item.items() if key != "source_record_id"}
                reason = " ".join(str(decision.get("reason") or "No unique bank candidate could be verified.").split())[:240]
                raw_evidence = decision.get("evidence")
                evidence_text = " ".join(str(raw_evidence or "Gemini batch arbitration").split())[:180]
                raw_choice = str(decision.get("decision") or "").lower().strip()
                candidate_id = decision.get("candidate_record_id")
                if isinstance(candidate_id, str) and candidate_id.lower().strip() in {"", "null", "none", "n/a"}:
                    candidate_id = None
                if raw_choice not in {"matched", "ambiguous"}:
                    raw_choice, candidate_id = "ambiguous", None
                    reason = "Gemini returned an invalid decision; retained for manual review."
                try:
                    confidence = max(0.0, min(1.0, float(decision.get("confidence", 0.0))))
                except (TypeError, ValueError):
                    confidence = 0.0
                decision = {
                    "decision": raw_choice,
                    "candidate_record_id": candidate_id,
                    "confidence": confidence,
                    "reason": reason,
                    "evidence": {"provider_summary": evidence_text, "provider": "GeminiArbitrationProvider", "model": self.model_name},
                }
                if decision.get("decision") == "matched" and decision.get("candidate_record_id") not in valid_candidates[source_id]:
                    decision = {**decision, "decision": "ambiguous", "candidate_record_id": None}
                by_source[source_id] = decision
            return by_source
        except Exception as e:
            # Return no decisions: the arbitration service retains deterministic
            # ambiguous outcomes without issuing more per-record requests.
            print(f"[GeminiArbitrationProvider] Batch fallback due to Error: {e}")
            return {}


def gemini_qa_provider_func(fact_set_dict: dict) -> str:
    """
    Given a GroundedFactSet (as dict), produce a conversational answer.
    """
    model_name = os.environ.get("GEMINI_MODEL", GEMINI_MODEL_DEFAULT)
    if not genai:
        return ""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    genai.configure(api_key=api_key)

    prompt = f"""
You are a Razorpay Finance AI Assistant answering a user's question about reconciliation.
Use ONLY the provided facts. DO NOT invent OR ADD ANY numbers, transaction IDs, or names.
If the facts are insufficient to fully answer, state what you know and that is it.

User Question: {fact_set_dict.get("question")}
Facts: {fact_set_dict.get("facts")}
Relevant Records: {fact_set_dict.get("record_ids")}

Respond cleanly in natural language.
"""
    model = genai.GenerativeModel(model_name)
    try:
        # Standard unstructured text mode
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.0),
            request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
        )
        return response.text
    except Exception as e:
        print(f"[Gemini QA] Fallback from error: {e}")
        return ""
