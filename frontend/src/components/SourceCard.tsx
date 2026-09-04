import React, { useRef } from 'react';
import { Upload, CheckCircle2, FileText, X } from 'lucide-react';

interface SourceCardProps {
  title: string;
  sourceKey: string;
  isMandatory?: boolean;
  file: File | null;
  onFileSelect: (file: File | null) => void;
  description: string;
}

export const SourceCard: React.FC<SourceCardProps> = ({
  title,
  isMandatory = false,
  file,
  onFileSelect,
  description,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelect(e.dataTransfer.files[0]);
    }
  };

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      onClick={() => fileInputRef.current?.click()}
      className={`group relative flex cursor-pointer flex-col justify-between rounded-xl border p-4 transition-all duration-200 ${
        file
          ? 'border-emerald-500/50 bg-emerald-50/40 dark:border-emerald-500/30 dark:bg-emerald-950/20'
          : isMandatory
          ? 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-md'
          : 'border-dashed border-slate-300 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 hover:border-slate-400 dark:hover:border-slate-700'
      }`}
    >
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".csv"
        className="hidden"
      />

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {file ? (
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          ) : (
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400">
              <Upload className="h-4 w-4" />
            </div>
          )}

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                {title}
              </h3>
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide uppercase ${
                  isMandatory
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                    : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                }`}
              >
                {isMandatory ? 'Mandatory' : 'Optional'}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{description}</p>
          </div>
        </div>

        {file && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onFileSelect(null);
            }}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title="Remove file"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Selected File Status */}
      <div className="mt-3 flex items-center justify-between border-t border-slate-200/60 dark:border-slate-800/60 pt-2.5">
        {file ? (
          <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400 truncate">
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{file.name}</span>
            <span className="text-[10px] text-emerald-600/70 dark:text-emerald-500/70 shrink-0">
              ({(file.size / 1024).toFixed(1)} KB)
            </span>
          </div>
        ) : (
          <span className="text-xs text-slate-400 dark:text-slate-500 italic">
            Drop CSV file or click to browse
          </span>
        )}
      </div>
    </div>
  );
};
