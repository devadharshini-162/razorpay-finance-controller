import os
import json
import traceback
from typing import List, Dict, Any, Type, Optional

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

GEMINI_MODEL_DEFAULT = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")

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

    def _generate_structured_json(self, prompt: str, schema_class: Type) -> dict:
        """Call Gemini demanding structured JSON output that conforms to a Pydantic schema."""
        model = genai.GenerativeModel(self.model_name)
        
        try:
            # We enforce application/json natively
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=schema_class,
                    temperature=0.0  # Must be purely deterministic translation
                ),
            )
            return json.loads(response.text)
        except Exception as e:
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


def gemini_qa_provider_func(fact_set_dict: dict) -> str:
    """
    Given a GroundedFactSet (as dict), produce a conversational answer.
    """
    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
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
            generation_config=genai.GenerationConfig(temperature=0.0)
        )
        return response.text
    except Exception as e:
        print(f"[Gemini QA] Fallback from error: {e}")
        return ""
