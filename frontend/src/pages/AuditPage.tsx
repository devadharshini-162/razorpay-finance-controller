import React, { useState } from 'react';
import { History, ExternalLink } from 'lucide-react';
import type { AuditRecord } from '../types';
import { EvidenceDrawer } from '../components/EvidenceDrawer';

interface AuditPageProps {
  auditRecords: AuditRecord[];
}

export const AuditPage: React.FC<AuditPageProps> = ({ auditRecords }) => {
  const [activeAudit, setActiveAudit] = useState<AuditRecord | null>(null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Audit Trail & Step Evidence
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Immutable log of pipeline execution, rule matching, and arbitration decisions.
          </p>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
          <History className="h-5 w-5" />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Audit ID</th>
                <th className="px-5 py-3">Record ID</th>
                <th className="px-5 py-3">Stage</th>
                <th className="px-5 py-3">Action</th>
                <th className="px-5 py-3">Method</th>
                <th className="px-5 py-3">Decision</th>
                <th className="px-5 py-3 text-right">Step Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 font-medium">
              {auditRecords.length > 0 ? (
                auditRecords.map((aud) => (
                  <tr
                    key={aud.audit_id}
                    onClick={() => setActiveAudit(aud)}
                    className="cursor-pointer hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="px-5 py-3.5 font-mono text-slate-400">{aud.audit_id}</td>
                    <td className="px-5 py-3.5 font-mono font-bold text-slate-900 dark:text-white">
                      {aud.record_id}
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider text-[11px]">
                      {aud.stage}
                    </td>
                    <td className="px-5 py-3.5 text-slate-700 dark:text-slate-300">{aud.action}</td>
                    <td className="px-5 py-3.5 font-mono text-slate-600 dark:text-slate-400">
                      {aud.method}
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900 dark:text-white">
                      {aud.decision}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveAudit(aud);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-50 dark:bg-blue-950/60 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-100"
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
                    No audit records generated.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Drawer */}
      {activeAudit && (
        <EvidenceDrawer
          isOpen={!!activeAudit}
          onClose={() => setActiveAudit(null)}
          title={`Audit Record: ${activeAudit.record_id}`}
          subtitle={`Stage: ${activeAudit.stage} | Action: ${activeAudit.action}`}
          evidence={activeAudit.evidence}
        />
      )}
    </div>
  );
};
