import React, { useState } from 'react';
import { Filter, ExternalLink } from 'lucide-react';
import type { ExceptionRecord } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { EvidenceDrawer } from '../components/EvidenceDrawer';

interface ExceptionsPageProps {
  exceptions: ExceptionRecord[];
}

export const ExceptionsPage: React.FC<ExceptionsPageProps> = ({ exceptions }) => {
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [activeException, setActiveException] = useState<ExceptionRecord | null>(null);

  const categories = Array.from(new Set(exceptions.map((e) => e.category)));

  const filteredExceptions = exceptions.filter((e) => {
    const matchesSev = selectedSeverity === 'all' || e.severity === selectedSeverity;
    const matchesCat = selectedCategory === 'all' || e.category === selectedCategory;
    return matchesSev && matchesCat;
  });

  return (
    <div className="space-y-6">
      {/* Top Header & Severity Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Exception Investigation Center
            </h2>
            <span className="rounded-full bg-rose-100 dark:bg-rose-950/60 px-2.5 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-400">
              {exceptions.length} Active Exceptions
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Identify discrepancies, fee mismatches, missing bank credits, and batch variances.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Category Dropdown */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400" />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 focus:outline-none"
            >
              <option value="all">All Categories ({exceptions.length})</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          {/* Severity Tabs */}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 p-1 text-xs">
            {['all', 'high', 'medium', 'low'].map((sev) => (
              <button
                key={sev}
                onClick={() => setSelectedSeverity(sev)}
                className={`rounded-lg px-3 py-1.5 font-semibold uppercase tracking-wider transition-all ${
                  selectedSeverity === sev
                    ? 'bg-white dark:bg-slate-900 text-rose-600 dark:text-rose-400 shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Exception Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Exception ID</th>
                <th className="px-5 py-3">Record ID</th>
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3">Severity</th>
                <th className="px-5 py-3">Reason & Discrepancy</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 font-medium">
              {filteredExceptions.length > 0 ? (
                filteredExceptions.map((exc) => (
                  <tr
                    key={exc.exception_id}
                    onClick={() => setActiveException(exc)}
                    className="cursor-pointer hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="px-5 py-3.5 font-mono text-slate-500">
                      {exc.exception_id}
                    </td>
                    <td className="px-5 py-3.5 font-mono font-bold text-slate-900 dark:text-white">
                      {exc.record_id}
                    </td>
                    <td className="px-5 py-3.5 font-semibold capitalize text-slate-700 dark:text-slate-300">
                      {exc.category.replace(/_/g, ' ')}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={exc.severity} type="severity" />
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-400 max-w-sm truncate">
                      {exc.reason}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveException(exc);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 text-xs font-semibold text-rose-700 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/60"
                      >
                        <span>Inspect Evidence</span>
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-400">
                    No active exceptions match your severity and category filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Structured Evidence Inspector Drawer */}
      {activeException && (
        <EvidenceDrawer
          isOpen={!!activeException}
          onClose={() => setActiveException(null)}
          title={`Exception Evidence: ${activeException.record_id}`}
          subtitle={`Category: ${activeException.category.replace(/_/g, ' ')} | Severity: ${activeException.severity.toUpperCase()}`}
          reason={activeException.reason}
          evidence={activeException.evidence}
        />
      )}
    </div>
  );
};
