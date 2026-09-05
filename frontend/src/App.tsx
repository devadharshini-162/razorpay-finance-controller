import { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  FileCheck,
  AlertTriangle,
  History,
  MessageSquareText,
  Upload,
  Play,
  RefreshCw,
  Sliders,
  FileSpreadsheet,
  Download,
} from 'lucide-react';
import { ThemeProvider } from './context/ThemeContext';
import { Navbar } from './components/Navbar';
import { SourceCard } from './components/SourceCard';
import { ValidationModal } from './components/ValidationModal';
import { OverviewPage } from './pages/OverviewPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { ExceptionsPage } from './pages/ExceptionsPage';
import { AuditPage } from './pages/AuditPage';
import { QAPage } from './pages/QAPage';
import type { ReconcileResponse } from './types';
import { runReconciliationApi, checkHealthApi, downloadReconciliationExport } from './services/api';

export function AppContent() {
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState('Missing Required Files');
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null);

  // File Upload State
  const [razorpayFile, setRazorpayFile] = useState<File | null>(null);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [ledgerFile, setLedgerFile] = useState<File | null>(null);
  const [fourthFile, setFourthFile] = useState<File | null>(null);
  const [primarySource, setPrimarySource] = useState<string>('razorpay');

  // Reconciliation Session Result State
  const [reconcileData, setReconcileData] = useState<ReconcileResponse | null>(null);

  // Health check on mount
  useEffect(() => {
    checkHealthApi()
      .then(() => setIsBackendHealthy(true))
      .catch(() => setIsBackendHealthy(false));
  }, []);

  const handleRunReconciliation = async () => {
    const errors: string[] = [];
    
    if (!bankFile) {
      errors.push("• Bank Statement CSV is MANDATORY");
    }
    if (!razorpayFile && !ledgerFile && !fourthFile) {
      errors.push("• At least ONE merchant source file must be provided:");
      errors.push("  - Razorpay Settlements, OR");
      errors.push("  - Merchant Ledger, OR");
      errors.push("  - Merchant Payout Export");
    }
    
    if (errors.length > 0) {
      setError(errors.join("\n"));
      setErrorTitle('Missing Required Files');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await runReconciliationApi(
        {
          razorpay_file: razorpayFile,
          bank_file: bankFile!,
          ledger_file: ledgerFile,
          fourth_file: fourthFile,
        },
        primarySource
      );

      setReconcileData(response);
    } catch (err: any) {
      setError(err.message || "Failed to execute reconciliation");
      setErrorTitle('Reconciliation Failed');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format: 'csv' | 'xlsx') => {
    if (!reconcileData) return;
    setExporting(format);
    try {
      await downloadReconciliationExport(reconcileData.session_id, format);
    } catch (err: any) {
      setError(err.message || 'Could not download the reconciliation export.');
      setErrorTitle('Download Failed');
    } finally {
      setExporting(null);
    }
  };

  const navItems = [
    { id: 'overview', label: 'Executive Overview', icon: LayoutDashboard },
    {
      id: 'decisions',
      label: 'Reconciled Transactions',
      icon: FileCheck,
      badge: reconcileData?.report.overall_resolved_records,
    },
    {
      id: 'exceptions',
      label: 'Exceptions Investigation',
      icon: AlertTriangle,
      badge: reconcileData?.report.total_exceptions,
      badgeColor: 'bg-rose-500 text-white',
    },
    { id: 'audit', label: 'Audit Trail', icon: History },
    { id: 'qa', label: 'Finance Q&A', icon: MessageSquareText },
  ];

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      <Navbar
        hasData={!!reconcileData}
        activeSource={reconcileData?.active_source_name}
        isBackendHealthy={isBackendHealthy}
      />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Source Upload Cards Workflow Grid */}
        <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5 mb-6">
            <div>
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  Financial Data Sources Workflow
                </h2>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Load settlements, bank statements, and optional merchant ledgers to execute reconciliation.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-slate-400" />
                <select
                  value={primarySource}
                  onChange={(e) => setPrimarySource(e.target.value)}
                  className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none"
                >
                  <option value="razorpay">Primary: Razorpay Settlements</option>
                  <option value="merchant_ledger">Primary: Merchant Ledger</option>
                  <option value="fourth_source">Primary: Merchant Payout Export</option>
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <SourceCard
              title="Razorpay Settlements"
              sourceKey="razorpay"
              isMandatory={true}
              file={razorpayFile}
              onFileSelect={setRazorpayFile}
              description="Standard settlement report with fee breakdown & UTR"
            />
            <SourceCard
              title="Bank Statement"
              sourceKey="bank"
              isMandatory={true}
              file={bankFile}
              onFileSelect={setBankFile}
              description="Bank credit statement containing settlement credits"
            />
            <SourceCard
              title="Merchant Ledger"
              sourceKey="ledger"
              isMandatory={false}
              file={ledgerFile}
              onFileSelect={setLedgerFile}
              description="Optional ERP / invoice accounting ledger"
            />
            <SourceCard
              title="Merchant Payout Export"
              sourceKey="fourth"
              isMandatory={false}
              file={fourthFile}
              onFileSelect={setFourthFile}
              description="Surprise 4th source export with distinct schema"
            />
          </div>

          {/* Primary Execution CTA */}
          <div className="mt-6 flex justify-end">
            <button
              onClick={handleRunReconciliation}
              disabled={loading || !bankFile}
              className="flex items-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold px-6 py-3 text-xs shadow-sm transition-all disabled:opacity-50"
            >
              {loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>Executing Pipeline & Arbitration...</span>
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" />
                  <span>Run Reconciliation Pipeline</span>
                </>
              )}
            </button>
          </div>
        </section>

        {/* Dashboard Navigation Tabs & View Section */}
        {reconcileData ? (
          <section className="space-y-6">
            {/* Tab Navigation */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-800">
              <div className="flex space-x-1 overflow-x-auto">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveTab(item.id)}
                    className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-bold transition-all shrink-0 ${
                      isActive
                        ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                        : 'border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                    {item.badge !== undefined && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
                          item.badgeColor || 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
              </div>
              <div className="flex items-center gap-2 pb-2 shrink-0">
                <span className="hidden md:inline text-xs font-medium text-slate-500 dark:text-slate-400">Download records</span>
                {(['csv', 'xlsx'] as const).map((format) => (
                  <button key={format} onClick={() => handleExport(format)} disabled={exporting !== null}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:border-blue-500 hover:text-blue-600 disabled:opacity-50">
                    <Download className="h-3.5 w-3.5" />
                    {exporting === format ? 'Preparing…' : format.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            {/* Active View */}
            {activeTab === 'overview' && (
              <OverviewPage report={reconcileData.report} onNavigateTab={setActiveTab} />
            )}
            {activeTab === 'decisions' && (
              <DecisionsPage decisions={reconcileData.decisions} />
            )}
            {activeTab === 'exceptions' && (
              <ExceptionsPage exceptions={reconcileData.exceptions} />
            )}
            {activeTab === 'audit' && (
              <AuditPage auditRecords={reconcileData.audit_records} />
            )}
            {activeTab === 'qa' && <QAPage sessionId={reconcileData.session_id} />}
          </section>
        ) : (
          /* Empty Initial State */
          <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 p-12 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
              <Upload className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-white">
              No Active Reconciliation Dataset
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
              Upload your Bank Statement CSV and Razorpay / Merchant CSV sources above to run your first reconciliation.
            </p>
          </div>
        )}
      </main>

      <ValidationModal
        isOpen={!!error}
        onClose={() => setError(null)}
        errorMessage={error || ''}
        title={errorTitle}
      />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
