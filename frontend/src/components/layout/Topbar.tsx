import React from 'react';
import { RefreshCw, Play, Wifi, WifiOff, Loader2 } from 'lucide-react';
import { useBackendStatus } from '../../context/BackendStatusContext';

interface TopbarProps {
  title?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onOpenCreateRun: () => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  title = 'Network Operations Center',
  onRefresh,
  isRefreshing = false,
  onOpenCreateRun,
}) => {
  const { isConnected, isChecking, checkConnection } = useBackendStatus();

  return (
    <header className="h-16 px-6 border-b border-slate-800 bg-[#0D1322]/90 backdrop-blur flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold text-white tracking-tight font-sans">
          {title}
        </h1>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/80">
          PROD-SIM
        </span>
      </div>

      <div className="flex items-center gap-3.5">
        {/* Backend Connection Indicator */}
        <div
          onClick={() => checkConnection()}
          title="Click to re-check backend connection"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs font-mono cursor-pointer transition-colors bg-slate-900/60 border-slate-800 hover:border-slate-700"
        >
          {isChecking ? (
            <>
              <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin" />
              <span className="text-slate-400">Pinging API...</span>
            </>
          ) : isConnected ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <Wifi className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-medium">FastAPI Connected</span>
            </>
          ) : (
            <>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
              <WifiOff className="w-3.5 h-3.5 text-rose-400" />
              <span className="text-rose-400 font-medium">Backend Offline</span>
            </>
          )}
        </div>

        {/* Refresh Action */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            title="Refresh current view"
            className="p-2 rounded-md border border-slate-800 bg-slate-900/60 hover:bg-slate-800 text-slate-300 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        )}

        {/* Quick Launch Run */}
        <button
          onClick={onOpenCreateRun}
          className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium font-sans shadow-[0_0_12px_rgba(6,182,212,0.25)] transition-all"
        >
          <Play className="w-3.5 h-3.5" />
          <span>New Resilience Run</span>
        </button>
      </div>
    </header>
  );
};

