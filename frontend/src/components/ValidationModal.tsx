import React from 'react';
import { AlertCircle, X } from 'lucide-react';

interface ValidationModalProps {
  isOpen: boolean;
  onClose: () => void;
  errorMessage: string;
  title?: string;
}

export const ValidationModal: React.FC<ValidationModalProps> = ({
  isOpen,
  onClose,
  errorMessage,
  title = 'Validation Error',
}) => {
  if (!isOpen) return null;

  const errorLines = errorMessage.split('\n').filter(line => line.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl">
        {/* Modal Header */}
        <div className="flex items-start gap-3 border-b border-slate-200 dark:border-slate-800 p-5">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400">
            <AlertCircle className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h2 className="font-bold text-slate-900 dark:text-white">{title}</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Please fix the following issues before running reconciliation
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="space-y-1 p-5">
          {errorLines.map((line, idx) => (
            <div
              key={idx}
              className={`text-sm ${
                line.startsWith('•')
                  ? 'font-semibold text-rose-700 dark:text-rose-400'
                  : 'text-slate-600 dark:text-slate-400 pl-4'
              }`}
            >
              {line}
            </div>
          ))}
        </div>

        {/* Modal Footer */}
        <div className="border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/80 p-4 flex justify-end gap-3 rounded-b-2xl">
          <button
            onClick={onClose}
            className="rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold px-4 py-2 text-sm transition-colors"
          >
            Got it, I'll fix this
          </button>
        </div>
      </div>
    </div>
  );
};
