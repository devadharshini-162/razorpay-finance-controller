import React, { useState } from 'react';
import { Search, ExternalLink } from 'lucide-react';
import type { ReconciliationDecision } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { EvidenceDrawer } from '../components/EvidenceDrawer';

interface DecisionsPageProps {
  decisions: ReconciliationDecision[];
}

export const DecisionsPage: React.FC<DecisionsPageProps> = ({ decisions }) => {
  const [search, setSearch] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [activeDecision, setActiveDecision] = useState<ReconciliationDecision | null>(null);

  const filteredDecisions = decisions.filter((d) => {
    const matchesStatus = selectedStatus === 'all' || d.decision === selectedStatus;
    const q = search.toLowerCase();
    const matchesSearch =
      !search ||
      d.source_record_id.toLowerCase().includes(q) ||
      (d.candidate_record_id && d.candidate_record_id.toLowerCase().includes(q)) ||
      d.method.toLowerCase().includes(q) ||
      d.reason.toLowerCase().includes(q);

    return matchesStatus && matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Top Header & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Reconciled Transactions Explorer
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Inspect source transactions reconciled against target bank credits.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Status Filter Pills */}
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 p-1 text-xs">
            {['all', 'matched', 'ambiguous', 'unmatched'].map((status) => (
              <button
                key={status}
                onClick={() => setSelectedStatus(status)}
                className={`rounded-lg px-3 py-1.5 font-semibold capitalize transition-all ${
                  selectedStatus === status
                    ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                {status}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="relative min-w-[220px]">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search Record ID / UTR..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 pl-9 pr-4 py-2 text-xs text-slate-900 dark:text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Source Record ID</th>
                <th className="px-5 py-3">Candidate Bank ID</th>
                <th className="px-5 py-3">Decision</th>
                <th className="px-5 py-3">Match Method</th>
                <th className="px-5 py-3">Confidence</th>
                <th className="px-5 py-3">Evaluation Reason</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 font-medium">
              {filteredDecisions.length > 0 ? (
                filteredDecisions.map((dec) => (
                  <tr
                    key={dec.decision_id}
                    onClick={() => setActiveDecision(dec)}
                    className="cursor-pointer hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="px-5 py-3.5 font-mono font-semibold text-slate-900 dark:text-white">
                      {dec.source_record_id}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-600 dark:text-slate-300">
                      {dec.candidate_record_id || '-'}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={dec.decision} type="decision" />
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-700 dark:text-slate-300">
                      {dec.method}
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900 dark:text-white">
                      {(dec.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-400 max-w-xs truncate">
                      {dec.reason}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveDecision(dec);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-50 dark:bg-blue-950/60 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/60"
                      >
                        <span>Evidence</span>
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                    No decisions matched your search and filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Inspector Drawer */}
      {activeDecision && (
        <EvidenceDrawer
          isOpen={!!activeDecision}
          onClose={() => setActiveDecision(null)}
          title={`Decision Evidence: ${activeDecision.source_record_id}`}
          subtitle={`Match Method: ${activeDecision.method} | Confidence: ${(activeDecision.confidence * 100).toFixed(0)}%`}
          reason={activeDecision.reason}
          evidence={activeDecision.evidence}
        />
      )}
    </div>
  );
};
