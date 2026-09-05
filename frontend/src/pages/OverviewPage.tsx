import React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  FileCheck2,
  Cpu,
  Layers,
  ArrowUpRight,
  Copy,
  Check,
  Download,
  ChevronDown,
} from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { MetricCard } from '../components/MetricCard';
import type { ReconciliationReport } from '../types';

interface OverviewPageProps {
  report: ReconciliationReport;
  onNavigateTab: (tab: string) => void;
  onExport: (report: 'reconciliation' | 'exceptions', format: 'csv' | 'xlsx') => void;
  exporting: string | null;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ report, onNavigateTab, onExport, exporting }) => {
  const [copied, setCopied] = React.useState(false);
  const [exportsOpen, setExportsOpen] = React.useState(false);

  // Prepare data for Recharts matching method breakdown
  const chartData = Object.entries(report.deterministic_method_breakdown || {}).map(([method, count]) => ({
    method: method.replace(/_/g, ' '),
    count,
  }));

  const handleCopySummary = () => {
    navigator.clipboard.writeText(report.summary_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Executive Health Prompt */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Reconciliation Executive Health
            </span>
          </div>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            {report.overall_resolution_rate >= 80 ? 'Reconciliation Status: Healthy' : 'Reconciliation Status: Attention Required'}
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {report.overall_resolved_records} of {report.total_source_records} source transactions successfully reconciled against bank statement.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => onNavigateTab('exceptions')}
            className="flex items-center gap-2 rounded-xl bg-slate-100 dark:bg-slate-800 px-4 py-2.5 text-xs font-bold text-rose-600 dark:text-rose-400 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all"
          >
            <AlertTriangle className="h-4 w-4" />
            <span>Investigate Exceptions ({report.total_exceptions})</span>
          </button>
          <button
            onClick={() => onNavigateTab('decisions')}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-blue-500 transition-all"
          >
            <span>View All Decisions</span>
            <ArrowUpRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Export Reports</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Matched records are included in reconciliation results. Ambiguous and unmatched records remain open in the exception report.
            </p>
          </div>
          <div className="relative self-start sm:self-auto">
            <button
              type="button"
              onClick={() => setExportsOpen((open) => !open)}
              disabled={exporting !== null}
              aria-expanded={exportsOpen}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:border-blue-500 hover:text-blue-600 disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5" />
              {exporting ? 'Preparing report…' : 'Download reports'}
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${exportsOpen ? 'rotate-180' : ''}`} />
            </button>
            {exportsOpen && (
              <div className="absolute right-0 z-10 mt-2 w-52 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1 shadow-lg">
                {(['reconciliation', 'exceptions'] as const).flatMap((reportType) =>
                  (['csv', 'xlsx'] as const).map((format) => {
                    const key = `${reportType}-${format}`;
                    const label = reportType === 'reconciliation' ? 'Reconciliation' : 'Exceptions';
                    return (
                      <button key={key} onClick={() => { setExportsOpen(false); onExport(reportType, format); }}
                        className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800">
                        <span>{label}</span>
                        <span className="font-semibold text-slate-400">{format.toUpperCase()}</span>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* KPI Cards Grid: 5 key numbers */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <MetricCard
          title="Overall Match Rate"
          value={`${report.overall_resolution_rate.toFixed(1)}%`}
          subtext={`${report.overall_resolved_records} resolved of ${report.total_source_records}`}
          icon={CheckCircle2}
          variant="success"
        />
        <MetricCard
          title="Deterministic Matches"
          value={report.deterministic_matches}
          subtext="Matched by deterministic rules"
          icon={FileCheck2}
          variant="info"
        />
        <MetricCard
          title="LLM-Resolved Matches"
          value={report.llm_resolved_matches}
          subtext="LLM arbitration matched (decision=matched)"
          icon={Cpu}
          variant={report.llm_resolved_matches > 0 ? 'info' : 'default'}
        />
        <MetricCard
          title="Still Ambiguous"
          value={report.ambiguous_records}
          subtext="LLM arbitration attempted, unresolved"
          icon={HelpCircle}
          variant={report.ambiguous_records > 0 ? 'warning' : 'success'}
        />
        <MetricCard
          title="Active Exceptions"
          value={report.total_exceptions}
          subtext={`${report.high_severity_exceptions} high severity requires review`}
          icon={AlertTriangle}
          variant={report.total_exceptions > 0 ? 'warning' : 'success'}
        />
      </div>

      {/* Match Analytics Chart & Secondary KPIs */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Method Breakdown Bar Chart */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Matching Method Distribution
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Breakdown of deterministic rule matches across transactions
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
              <Layers className="h-4 w-4" />
            </div>
          </div>

          <div className="h-64 w-full">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    dataKey="method"
                    tick={{ fontSize: 11 }}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#334155',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '12px',
                    }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No deterministic match data available.
              </div>
            )}
          </div>
        </div>

        {/* Unmatched & Ambiguous Summary */}
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">
              Unresolved Breakdown
            </h3>

            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/40 dark:bg-amber-950/20 p-3.5">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    <HelpCircle className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-slate-900 dark:text-white">Ambiguous Records</div>
                    <div className="text-[11px] text-slate-500">Multiple bank candidates detected</div>
                  </div>
                </div>
                <span className="text-base font-extrabold text-amber-600 dark:text-amber-400">
                  {report.ambiguous_records}
                </span>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50/40 dark:bg-rose-950/20 p-3.5">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400">
                    <AlertTriangle className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-slate-900 dark:text-white">Unmatched Records</div>
                    <div className="text-[11px] text-slate-500">No bank statement credit found</div>
                  </div>
                </div>
                <span className="text-base font-extrabold text-rose-600 dark:text-rose-400">
                  {report.unmatched_records}
                </span>
              </div>
            </div>
          </div>

          {/* Report Text Copy Card */}
          <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 p-3 flex items-center justify-between">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
              Audit Report Text
            </span>
            <button
              onClick={handleCopySummary}
              className="flex items-center gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy Summary'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
