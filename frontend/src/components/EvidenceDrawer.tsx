import React, { useState } from 'react';
import { X, Code, FileText } from 'lucide-react';

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
  const [showRawJson, setShowRawJson] = useState(false);

  if (!isOpen) return null;

  // Flatten evidence object into clean key-value pairs
  const renderStructuredEvidence = (obj: Record<string, any>) => {
    const entries: { label: string; value: string }[] = [];

    const formatVal = (v: any): string => {
      if (v === null || v === undefined) return '-';
      if (typeof v === 'boolean') return v ? 'True' : 'False';
      if (typeof v === 'object') return JSON.stringify(v);
      return String(v);
    };

    Object.entries(obj).forEach(([key, val]) => {
      const formattedKey = key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (l) => l.toUpperCase());

      if (val && typeof val === 'object' && !Array.isArray(val)) {
        Object.entries(val).forEach(([subK, subV]) => {
          const subLabel = `${formattedKey} → ${subK.replace(/_/g, ' ')}`;
          entries.push({ label: subLabel, value: formatVal(subV) });
        });
      } else {
        entries.push({ label: formattedKey, value: formatVal(val) });
      }
    });

    return entries;
  };

  const evidencePairs = renderStructuredEvidence(evidence);

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
              <button
                onClick={() => setShowRawJson(!showRawJson)}
                className="flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
              >
                <Code className="h-3.5 w-3.5" />
                <span>{showRawJson ? 'View Table' : 'View Raw JSON'}</span>
              </button>
            </div>

            {showRawJson ? (
              <pre className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs font-mono text-emerald-400 overflow-x-auto">
                {JSON.stringify(evidence, null, 2)}
              </pre>
            ) : evidencePairs.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">Evidence Field</th>
                      <th className="px-4 py-2.5 font-semibold">Value</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800 font-mono">
                    {evidencePairs.map((pair, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                        <td className="px-4 py-2.5 font-sans font-medium text-slate-600 dark:text-slate-300">
                          {pair.label}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-900 dark:text-white break-all">
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
