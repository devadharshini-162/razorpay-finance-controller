export interface ReconciliationReport {
  total_source_records: number;
  overall_resolved_records: number;
  overall_resolution_rate: number;
  overall_unresolved_rate: number;
  deterministic_matches: number;
  llm_resolved_matches: number;
  ambiguous_records: number;
  unmatched_records: number;
  total_exceptions: number;
  high_severity_exceptions: number;
  deterministic_method_breakdown: Record<string, number>;
  summary_text: string;
}

export interface ReconciliationDecision {
  decision_id: string;
  source_record_id: string;
  candidate_record_id: string | null;
  decision: 'matched' | 'ambiguous' | 'unmatched';
  method: string;
  confidence: number;
  reason: string;
  evidence: Record<string, any>;
}

export interface ExceptionRecord {
  exception_id: string;
  record_id: string;
  category: 'amount_mismatch' | 'date_mismatch' | 'duplicate' | 'fee_mismatch' | 'missing_counterparty' | 'ambiguous_match' | 'batch_settlement' | 'refund_mismatch' | 'unknown';
  severity: 'low' | 'medium' | 'high';
  reason: string;
  confidence: number;
  evidence: Record<string, any>;
}

export interface AuditRecord {
  audit_id: string;
  record_id: string;
  stage: string;
  action: string;
  method: string;
  decision: string;
  evidence: Record<string, any>;
}

export interface ReconcileResponse {
  session_id: string;
  active_source_name: string;
  report: ReconciliationReport;
  decisions: ReconciliationDecision[];
  exceptions: ExceptionRecord[];
  audit_records: AuditRecord[];
}

export interface QAResponse {
  answer: string;
  evidence: Record<string, any>;
}

export interface QAMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  evidence?: Record<string, any>;
  timestamp: string;
}
