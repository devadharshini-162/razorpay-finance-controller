import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtext?: string;
  icon: LucideIcon;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtext,
  icon: Icon,
  variant = 'default',
}) => {
  const getVariantStyles = () => {
    switch (variant) {
      case 'success':
        return 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400';
      case 'warning':
        return 'border-amber-200 dark:border-amber-900/50 bg-amber-50/30 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400';
      case 'danger':
        return 'border-rose-200 dark:border-rose-900/50 bg-rose-50/30 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400';
      case 'info':
        return 'border-blue-200 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400';
      default:
        return 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400';
    }
  };

  return (
    <div className={`flex flex-col justify-between rounded-xl border p-5 shadow-xs transition-all ${getVariantStyles()}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-wider uppercase text-slate-500 dark:text-slate-400">
          {title}
        </span>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800">
          <Icon className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-3">
        <div className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          {value}
        </div>
        {subtext && (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 font-medium">
            {subtext}
          </p>
        )}
      </div>
    </div>
  );
};
