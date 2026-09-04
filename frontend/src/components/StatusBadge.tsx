import React from 'react';

interface StatusBadgeProps {
  status: string;
  type?: 'decision' | 'severity' | 'method';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, type = 'decision' }) => {
  const val = status.toLowerCase();

  if (type === 'severity') {
    if (val === 'high') {
      return (
        <span className="inline-flex items-center rounded-md bg-rose-50 dark:bg-rose-950/60 px-2 py-1 text-xs font-semibold text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
          ● HIGH SEVERITY
        </span>
      );
    }
    if (val === 'medium') {
      return (
        <span className="inline-flex items-center rounded-md bg-amber-50 dark:bg-amber-950/60 px-2 py-1 text-xs font-semibold text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
          ▲ MEDIUM SEVERITY
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-md bg-blue-50 dark:bg-blue-950/60 px-2 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
        ℹ LOW SEVERITY
      </span>
    );
  }

  if (type === 'decision') {
    if (val === 'matched') {
      return (
        <span className="inline-flex items-center rounded-md bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
          ✓ Matched
        </span>
      );
    }
    if (val === 'ambiguous') {
      return (
        <span className="inline-flex items-center rounded-md bg-amber-50 dark:bg-amber-950/60 px-2.5 py-1 text-xs font-semibold text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
          ⚠ Ambiguous
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-md bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 text-xs font-semibold text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
        ✕ Unmatched
      </span>
    );
  }

  return (
    <span className="inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 text-xs font-mono text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
      {status}
    </span>
  );
};
