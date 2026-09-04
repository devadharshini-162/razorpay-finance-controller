import type { ReconcileResponse, QAResponse } from '../types';

export async function runReconciliationApi(
  files: {
    razorpay_file?: File | null;
    bank_file: File;
    ledger_file?: File | null;
    fourth_file?: File | null;
  },
  primarySourceName: string = 'razorpay'
): Promise<ReconcileResponse> {
  const formData = new FormData();
  formData.append('bank_file', files.bank_file);
  
  if (files.razorpay_file) {
    formData.append('razorpay_file', files.razorpay_file);
  }
  if (files.ledger_file) {
    formData.append('ledger_file', files.ledger_file);
  }
  if (files.fourth_file) {
    formData.append('fourth_file', files.fourth_file);
  }
  formData.append('primary_source_name', primarySourceName);

  const res = await fetch('/api/reconcile', {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: 'Failed to run reconciliation' }));
    throw new Error(errorData.detail || 'Reconciliation failed');
  }

  return await res.json();
}

export async function askQuestionApi(sessionId: string, question: string): Promise<QAResponse> {
  const res = await fetch('/api/qa/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      session_id: sessionId,
      question,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: 'Failed to ask question' }));
    throw new Error(errorData.detail || 'Q&A failed');
  }

  return await res.json();
}

export async function checkHealthApi(): Promise<{ status: string; active_sessions: number }> {
  const res = await fetch('/api/health');
  if (!res.ok) throw new Error('API server unavailable');
  return await res.json();
}

export async function downloadReconciliationExport(sessionId: string, format: 'csv' | 'xlsx'): Promise<void> {
  const res = await fetch(`/api/session/${sessionId}/export?format=${format}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 404) {
      throw new Error('Export is unavailable on the running backend. Restart the backend, then run reconciliation again.');
    }
    throw new Error(body.detail || `Could not create the ${format.toUpperCase()} export.`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `reconciliation.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
