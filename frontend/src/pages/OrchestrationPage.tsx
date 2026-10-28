import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  GitBranch,
  RefreshCw,
} from 'lucide-react';
import { orchestrationApi } from '../api/orchestration';
import { OrchestrationRunResponse } from '../api/types';
import { WorkflowGraph } from '../components/orchestration/WorkflowGraph';
import { ApprovalPanel } from '../components/orchestration/ApprovalPanel';
import { RunStatusPanel } from '../components/orchestration/RunStatusPanel';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { EmptyState } from '../components/common/EmptyState';
import { StatusBadge } from '../components/common/StatusBadge';

const TERMINAL_STATUSES = new Set([
  'completed',
  'completed_healthy',
  'completed_no_action',
  'failed',
  'rejected',
  'verification_failed',
  'partial_success',
]);

export const OrchestrationPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedRunId = searchParams.get('run_id');

  const [runsList, setRunsList] = useState<OrchestrationRunResponse[]>([]);
  const [currentRun, setCurrentRun] = useState<OrchestrationRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollingRef = useRef<number | null>(null);

  // Fetch all runs and the active run
  const loadData = useCallback(async (selectedId?: string, silent: boolean = false) => {
    if (!silent) setIsRefreshing(true);
    try {
      const runs = await orchestrationApi.listRuns();
      setRunsList(runs);

      const targetId = selectedId || requestedRunId || (runs.length > 0 ? runs[0].run_id : null);

      if (targetId) {
        const runData = await orchestrationApi.getRun(targetId);
        setCurrentRun(runData);
        if (targetId !== requestedRunId) {
          setSearchParams({ run_id: targetId }, { replace: true });
        }
      } else {
        setCurrentRun(null);
      }
      setError(null);
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to fetch orchestration runs');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [requestedRunId, setSearchParams]);

  useEffect(() => {
    loadData(requestedRunId || undefined);
  }, [loadData, requestedRunId]);

  // Clean polling implementation:
  // Polls only if run is active or awaiting approval; terminates when run reaches terminal state.
  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (!currentRun) return;

    const isTerminal = TERMINAL_STATUSES.has(currentRun.status);

    if (!isTerminal) {
      pollingRef.current = window.setInterval(async () => {
        try {
          const fresh = await orchestrationApi.getRun(currentRun.run_id);
          setCurrentRun(fresh);
          if (TERMINAL_STATUSES.has(fresh.status) && pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        } catch {
          // If poll fails, suppress error to not disrupt UI
        }
      }, 2500);
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [currentRun?.run_id, currentRun?.status]);

  const handleSelectRun = (runId: string) => {
    setSearchParams({ run_id: runId });
    loadData(runId);
  };

  const handleDecisionSubmitted = (updatedRun: OrchestrationRunResponse) => {
    setCurrentRun(updatedRun);
    loadData(updatedRun.run_id, true);
  };

  if (loading && runsList.length === 0) {
    return <LoadingState message="Connecting to LangGraph Orchestration Layer..." />;
  }

  if (error && !currentRun) {
    return (
      <ErrorState
        title="Orchestration Service Error"
        message={error}
        onRetry={() => loadData()}
      />
    );
  }

  if (runsList.length === 0) {
    return (
      <EmptyState
        title="No Orchestration Runs Found"
        description="Launch an autonomous resilience coordination run using the button above to execute Red Agent disruption, Blue Sentinel detection, and validated recovery."
        icon={GitBranch}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Top bar with run selector & refresh */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400 uppercase">Selected Run:</span>
            <select
              value={currentRun?.run_id || ''}
              onChange={(e) => handleSelectRun(e.target.value)}
              className="px-3 py-1.5 rounded-md bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            >
              {runsList.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id} — [{r.status}] &ldquo;{r.goal.slice(0, 30)}&rdquo;
                </option>
              ))}
            </select>
          </div>

          {currentRun && (
            <div className="hidden sm:flex items-center gap-2">
              <StatusBadge status={currentRun.status} size="sm" />
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {currentRun && !TERMINAL_STATUSES.has(currentRun.status) && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 bg-cyan-950/40 px-2.5 py-1 rounded border border-cyan-500/30">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              <span>Live Graph Checkpoint Polling</span>
            </div>
          )}

          <button
            onClick={() => loadData(currentRun?.run_id)}
            disabled={isRefreshing}
            className="p-1.5 rounded-md border border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {currentRun && (
        <>
          {/* LangGraph Stage Visualization */}
          <WorkflowGraph run={currentRun} />

          {/* Human-in-the-Loop Operator Gate */}
          <ApprovalPanel
            run={currentRun}
            onDecisionSubmitted={handleDecisionSubmitted}
          />

          {/* Detailed Status & Observability Panel */}
          <RunStatusPanel run={currentRun} />
        </>
      )}
    </div>
  );
};
