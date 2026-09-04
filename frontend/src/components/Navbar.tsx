import React from 'react';
import { Zap, Moon, Sun, ShieldCheck } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface NavbarProps {
  hasData: boolean;
  activeSource?: string;
  isBackendHealthy: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ hasData, activeSource, isBackendHealthy }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md transition-colors">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
            <Zap className="h-5 w-5 fill-current" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
                Razorpay AI Controller
              </h1>
              <span className="inline-flex items-center rounded-full bg-blue-50 dark:bg-blue-950/60 px-2 py-0.5 text-xs font-semibold text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                Merchant Ops
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Multi-source Settlement & Reconciliation Engine
            </p>
          </div>
        </div>

        {/* Right Status Controls */}
        <div className="flex items-center gap-4">
          {/* Backend Status Indicator */}
          <div className="flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-1 text-xs text-slate-600 dark:text-slate-300">
            <span className={`h-2 w-2 rounded-full ${isBackendHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
            <span className="font-medium">{isBackendHealthy ? 'System Healthy' : 'Backend Connecting'}</span>
          </div>

          {/* Active Reconciliation Dataset Badge */}
          {hasData && (
            <div className="hidden md:flex items-center gap-1.5 rounded-full border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/40 px-3 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>Active: <strong className="capitalize">{activeSource?.replace('_', ' ')}</strong></span>
            </div>
          )}

          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </header>
  );
};
