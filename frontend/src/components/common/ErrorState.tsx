import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Service Error Encountered',
  message,
  onRetry,
  className = 'py-12',
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-6 text-center rounded-lg border border-rose-500/30 bg-rose-950/20 max-w-xl mx-auto my-6 ${className}`}
    >
      <div className="p-3 rounded-full bg-rose-900/40 border border-rose-500/30 text-rose-400 mb-3">
        <AlertTriangle className="w-6 h-6" />
      </div>
      <h3 className="text-base font-semibold text-rose-200">{title}</h3>
      <p className="mt-2 text-xs font-mono text-rose-300/80 leading-relaxed bg-black/40 p-3 rounded border border-rose-900/40 w-full text-left break-words">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-md bg-rose-600 hover:bg-rose-500 text-white transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry Request
        </button>
      )}
    </div>
  );
};

