import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  submessage?: string;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading telemetry & orchestration state...',
  submessage,
  className = 'py-16',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center text-center ${className}`}>
      <div className="relative">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <div className="absolute inset-0 w-8 h-8 rounded-full blur-sm bg-cyan-500/20 animate-pulse pointer-events-none" />
      </div>
      <p className="mt-4 text-sm font-medium text-slate-300 font-mono tracking-wide">
        {message}
      </p>
      {submessage && (
        <p className="mt-1 text-xs text-slate-500 max-w-sm">
          {submessage}
        </p>
      )}
    </div>
  );
};

