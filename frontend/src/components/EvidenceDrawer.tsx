import React from 'react';
import { X, FileText } from 'lucide-react';

interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  reason?: string;
  evidence: Record<string, any>;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  reason,
  evidence,
}) => {
  if (!isOpen) return null;

  // Format values to be human-readable
  const formatValue = (v: any): string => {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'boolean') return v ? '✓ Yes' : '✗ No';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return v.toLocaleString();
      return v.toFixed(2);
    }
    if (Array.isArray(v)) {
      if (v.length === 0) return '(empty)';
      if (typeof v[0] === 'string' && v.every(item => typeof item === 'string')) {
        return v.join(', ');
      }
      return `${v.length} item${v.length === 1 ? '' : 's'}`;
    }
    if (typeof v === 'object') return '(see details)';
    return String(v);
  };

  // Prettify key names
  const prettifyKey = (key: string): string => {
    return key
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .replace(/\b\w/g, (l) => l.toUpperCase())
      .trim();
  };

  // Flatten evidence object into clean key-value pairs
  const renderStructuredEvidence = (obj: Record<string, any>) => {
    const entries: { label: string; value: string; rawValue?: any }[] = [];

    Object.entries(obj).forEach(([key, val]) => {
      const formattedKey = prettifyKey(key);

      if (val && typeof val === 'object' && !Array.isArray(val) && Object.keys(val).length > 0) {
        // Nested object - expand it
        Object.entries(val).forEach(([subK, subV]) => {
          const subLabel = `${formattedKey} / ${prettifyKey(subK)}`;
          entries.push({ label: subLabel, value: formatValue(subV), rawValue: subV });
        });
      } else if (Array.isArray(val) && val.length > 0) {
        if (val.every(item => item && typeof item === 'object' && !Array.isArray(item))) {
          val.forEach((item, itemIndex) => {
            Object.entries(item).forEach(([subKey, subValue]) => {
              entries.push({
                label: `${formattedKey} ${itemIndex + 1} / ${prettifyKey(subKey)}`,
                value: formatValue(subValue),
                rawValue: subValue,
              });
            });
          });
        } else {
          entries.push({ label: formattedKey, value: val.map(String).join(', '), rawValue: val });
        }
      } else {
        entries.push({ label: formattedKey, value: formatValue(val), rawValue: val });
      }
    });

    return entries;
  };

  const evidencePairs = renderStructuredEvidence(evidence);
  const bankCandidates = Array.isArray(evidence.bank_candidates) ? evidence.bank_candidates : [];
  const generalEvidencePairs = evidencePairs.filter((pair) => !pair.label.startsWith('Bank Candidates'));

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/50 backdrop-blur-xs transition-opacity">
      <div className="flex h-full w-full max-w-lg flex-col bg-white dark:bg-slate-900 shadow-2xl border-l border-slate-200 dark:border-slate-800">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">{title}</h2>
              {subtitle && <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Reason Section */}
          {reason && (
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 p-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Evaluation Reason
              </span>
              <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                {reason}
              </p>
            </div>
          )}

          {/* Structured Evidence Table */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Match & Fact Evidence
              </h3>
            </div>

            {bankCandidates.length > 0 && (
              <div className="mb-4 space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Bank candidates to compare</h3>
                {bankCandidates.map((candidate, index) => (
                  <div key={candidate.record_id || index} className="rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/20 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-slate-900 dark:text-white">{candidate.record_id || `Candidate ${index + 1}`}</span>
                      <span className="rounded-full bg-amber-100 dark:bg-amber-900/50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:text-amber-300">Candidate {index + 1}</span>
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                      <div><dt className="text-slate-500">Amount</dt><dd className="font-semibold text-slate-900 dark:text-white">{candidate.amount ? `₹${candidate.amount}` : 'Not supplied'}</dd></div>
                      <div><dt className="text-slate-500">Date</dt><dd className="font-semibold text-slate-900 dark:text-white">{candidate.date || 'Not supplied'}</dd></div>
                      <div className="col-span-2"><dt className="text-slate-500">Reference</dt><dd className="font-semibold text-slate-900 dark:text-white">{candidate.reference || 'Not supplied'}</dd></div>
                      {candidate.description && <div className="col-span-2"><dt className="text-slate-500">Description</dt><dd className="font-semibold text-slate-900 dark:text-white">{candidate.description}</dd></div>}
                    </dl>
                  </div>
                ))}
              </div>
            )}
            {generalEvidencePairs.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">Evidence Field</th>
                      <th className="px-4 py-2.5 font-semibold">Value</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {generalEvidencePairs.map((pair, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                        <td className="px-4 py-2.5 font-medium text-slate-600 dark:text-slate-300 whitespace-nowrap">
                          {pair.label}
                        </td>
                        <td className="px-4 py-2.5 text-slate-900 dark:text-white break-words max-w-xs">
                          {pair.value}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-800 p-6 text-center text-xs text-slate-400">
                No extra evidence metadata recorded.
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="border-t border-slate-200 dark:border-slate-800 p-4 bg-slate-50 dark:bg-slate-900/80 text-right">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-900 dark:bg-slate-100 px-4 py-2 text-xs font-semibold text-white dark:text-slate-900 hover:opacity-90 transition-opacity"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
