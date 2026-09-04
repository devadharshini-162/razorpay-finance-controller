import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.gemini_providers import GeminiLLMProvider, GeminiArbitrationProvider, gemini_qa_provider_func
from app.models.mapping import MappingResult
from app.models.canonical import CanonicalTransaction
from app.ui_app import run_pipeline

class TestGeminiIntegrations:
    
    @patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key"}, clear=True)
    @patch("app.services.gemini_providers.genai.GenerativeModel.generate_content")
    def test_gemini_llm_provider_success(self, mock_generate):
        # Mock structured response
        mock_response = MagicMock()
        mock_response.text = '{"column_mapping": {"Raw Ref": "reference"}, "unmapped_columns": [], "confidence": 0.95, "explanation": "Looks good"}'
        mock_generate.return_value = mock_response
        
        provider = GeminiLLMProvider()
        res = provider.map_schema("test_source", ["Raw Ref"], [{"Raw Ref": "123"}])
        
        assert res.column_mapping == {"Raw Ref": "reference"}
        assert res.confidence == 0.95
        assert res.audit_info["provider"] == "GeminiLLMProvider"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key"}, clear=True)
    @patch("app.services.gemini_providers.genai.GenerativeModel.generate_content")
    def test_gemini_llm_provider_malformed(self, mock_generate):
        # Mock API returning malformed JSON
        mock_response = MagicMock()
        mock_response.text = '{"column_mapping": "Whoops I forgot how to write json'
        mock_generate.return_value = mock_response
        
        provider = GeminiLLMProvider()
        res = provider.map_schema("test_source", ["Raw Ref"], [])
        
        # Should gracefully degrade
        assert res.column_mapping == {}
        assert "Raw Ref" in res.unmapped_columns
        assert res.confidence == 0.0
        assert "Fallback" in res.audit_info["provider"]

    @patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key"}, clear=True)
    @patch("app.services.gemini_providers.genai.GenerativeModel.generate_content")
    def test_gemini_arbitrator_success(self, mock_generate):
        mock_response = MagicMock()
        mock_response.text = '{"decision": "matched", "candidate_record_id": "c1", "confidence": 0.8, "reason": "Amounts match"}'
        mock_generate.return_value = mock_response
        
        provider = GeminiArbitrationProvider()
        src = CanonicalTransaction(record_id="s1", source="test", transaction_type="unknown", amount=100.0)
        c1 = CanonicalTransaction(record_id="c1", source="test2", transaction_type="unknown", amount=100.0)
        
        res = provider.resolve_ambiguity(src, [c1], {})
        
        assert res["decision"] == "matched"
        assert res["candidate_record_id"] == "c1"
        assert res["confidence"] == 0.8

    @patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key"}, clear=True)
    @patch("app.services.gemini_providers.genai.GenerativeModel.generate_content")
    def test_gemini_arbitrator_invalid_candidate_id(self, mock_generate):
        # Gemini hallucinates an ID that doesn't exist
        mock_response = MagicMock()
        mock_response.text = '{"decision": "matched", "candidate_record_id": "c999", "confidence": 0.9, "reason": "I hallucinated this"}'
        mock_generate.return_value = mock_response
        
        provider = GeminiArbitrationProvider()
        src = CanonicalTransaction(record_id="s1", source="test", transaction_type="unknown", amount=100.0)
        c1 = CanonicalTransaction(record_id="c1", source="test2", transaction_type="unknown", amount=100.0)
        
        res = provider.resolve_ambiguity(src, [c1], {})
        
        # Engine should catch invalid ID and force ambiguous fallback
        assert res["decision"] == "ambiguous"
        assert res["candidate_record_id"] is None

    @patch.dict(os.environ, {}, clear=True)
    def test_gemini_missing_api_key(self):
        # Should raise ValueError
        with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not set."):
            GeminiLLMProvider()

    @patch.dict(os.environ, {"GEMINI_ENABLED": "false", "GEMINI_API_KEY": "exists"}, clear=True)
    def test_ui_app_deterministic_fallback_when_disabled(self):
        class MemFile:
            def __init__(self, path):
                with open(path, 'rb') as f:
                    self._data = f.read()
            def read(self):
                return self._data
                
        # Even with an API key, if GEMINI_ENABLED is false, ui_app should preserve the deterministic baseline
        res = run_pipeline(
            razorpay_file=MemFile('data/raw/razorpay_settlements.csv'), 
            bank_file=MemFile('data/raw/bank_statement.csv')
        )
        report = res['report']
        
        # Frozen baseline metrics must hold
        assert report.total_source_records == 81
        assert report.deterministic_matches == 65
        assert report.llm_resolved_matches == 0
        assert report.ambiguous_records == 13
        assert report.unmatched_records == 3
