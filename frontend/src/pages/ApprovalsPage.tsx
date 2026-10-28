import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Lock,
  User,
  FileText,
  ShieldCheck,
  Clock,
} from 'lucide-react';
import { orchestrationApi } from '../api/orchestration';
import { OrchestrationRunResponse } from '../api/types';
import { ConfirmationDialog } from '../components/common/ConfirmationDialog';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingState } from '../components/common/LoadingState';
import { EmptyState } from '../components/common/EmptyState';

export const ApprovalsPage: React.FC = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [pendingRuns, setPendingRuns] = useState<OrchestrationRunResponse[]>([]);
  const [resolvedRuns, setResolvedRuns] = useState<OrchestrationRunResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Operator input state per run
  const [operatorId, setOperatorId] = useState('secops_lead');
  const [notes, setNotes] = useState('');

  // Confirmation dialog state
  const [pendingAction, setPendingAction] = useState<{
    runId: string;
    recId: string;
    decision: 'approve' | 'reject';
    actionType: string;
    target?: string | null;
  } | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchApprovals = useCallback(async () => {
    try {
      const allRuns = await orchestrationApi.listRuns();
      const pending = allRuns.filter(
        (r) => r.pending_approval || r.status === 'pending_approval'
      );
      const resolved = allRuns.filter(
        (r) => r.approval_status === 'approved' || r.approval_status === 'rejected'
      );

      setPendingRuns(pending);
      setResolvedRuns(resolved);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch approval queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const handleDecision = async () => {
    if (!pendingAction) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await orchestrationApi.resumeRun(pendingAction.runId, {
        decision: pendingAction.decision,
        recommendation_id: pendingAction.recId,
        approver: operatorId.trim() || 'operator',
        notes: notes.trim(),
      });

      setPendingAction(null);
      setNotes('');
      fetchApprovals();
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to process decision');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading && pendingRuns.length === 0 && resolvedRuns.length === 0) {
    return <LoadingState message="Scanning for Active Operator Approval Gates..." />;
  }

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div>
          <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <Lock className="w-4 h-4 text-amber-400" />
            Human-in-the-Loop Operator Authorization Queue
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Strict safety requirement: No state-changing network recovery action executes without explicit human verification.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Pending Actions:</span>
          <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">
            {pendingRuns.length} Active
          </span>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Pending Approvals List */}
      <div className="space-y-4">
        <h3 className="text-xs font-mono font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400" />
          Pending Authorization Requests ({pendingRuns.length})
        </h3>

        {pendingRuns.map((run) => {
          const rec = run.recommendation;
          const recId = run.recommendation_id || rec?.recommendation_id || 'unknown';

          return (
            <div
              key={run.run_id}
              className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-6 shadow-xl space-y-4 font-mono text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-amber-500/30">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-white">Run ID: {run.run_id}</span>
                  <StatusBadge status={run.status} size="sm" />
                </div>
                <div className="text-slate-400 text-[11px]">
                  Goal: &ldquo;{run.goal}&rdquo;
                </div>
              </div>

              {/* Action and Target */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3.5 rounded bg-slate-900/80 border border-slate-800 space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase block">Proposed Mitigation</span>
                  <div className="text-cyan-300 font-bold text-sm">{rec?.action_type || 'N/A'}</div>
                  <div className="text-slate-400">Target: <span className="text-amber-300 font-semibold">{rec?.target || 'All affected'}</span></div>
                  <div className="text-slate-500 text-[11px]">Recommendation ID: {recId}</div>
                </div>

                <div className="p-3.5 rounded bg-slate-900/80 border border-slate-800 space-y-1">
                  <span className="text-[10px] text-slate-500 uppercase block">Expected Operational Effect</span>
                  <p className="text-slate-200 text-xs leading-relaxed">
                    {rec?.expected_effect || 'Restores network link/node availability to recover reachable traffic flows.'}
                  </p>
                  <div className="text-emerald-400 text-[11px] flex items-center gap-1 pt-1">
                    <CheckCircle className="w-3.5 h-3.5" /> Preconditions Verified by Blue Sentinel
                  </div>
                </div>
              </div>

              {/* Rationale */}
              {rec?.reason && (
                <div className="p-3 rounded bg-slate-900/60 border border-slate-800 text-slate-300 text-xs">
                  <span className="text-[10px] text-slate-500 uppercase block mb-1">Evidence-Grounded Rationale</span>
                  {rec.reason}
                </div>
              )}

              {/* Operator Inputs */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3 border-t border-amber-500/20">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1 flex items-center gap-1">
                    <User className="w-3 h-3" /> Operator Handle
                  </label>
                  <input
                    type="text"
                    value={operatorId}
                    onChange={(e) => setOperatorId(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs rounded bg-slate-900 border border-slate-700 text-white font-mono focus:border-amber-400 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1 flex items-center gap-1">
                    <FileText className="w-3 h-3" /> Decision Notes / Rationale
                  </label>
                  <input
                    type="text"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Optional operator notes"
                    className="w-full px-3 py-1.5 text-xs rounded bg-slate-900 border border-slate-700 text-white font-mono focus:border-amber-400 focus:outline-none"
                  />
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-amber-500/20">
                <button
                  onClick={() => navigate(`/orchestration?run_id=${encodeURIComponent(run.run_id)}`)}
                  className="text-xs text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1"
                >
                  Inspect Full Run Graph &rarr;
                </button>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() =>
                      setPendingAction({
                        runId: run.run_id,
                        recId,
                        decision: 'reject',
                        actionType: rec?.action_type || 'Unknown',
                        target: rec?.target,
                      })
                    }
                    className="px-4 py-2 rounded bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-500/40 text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
                  >
                    <XCircle className="w-4 h-4 text-rose-400" />
                    Reject Mitigation
                  </button>

                  <button
                    onClick={() =>
                      setPendingAction({
                        runId: run.run_id,
                        recId,
                        decision: 'approve',
                        actionType: rec?.action_type || 'Unknown',
                        target: rec?.target,
                      })
                    }
                    className="px-5 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Authorize &amp; Execute Recovery
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {pendingRuns.length === 0 && (
          <EmptyState
            title="All Operational Gates Cleared"
            description="There are currently no network recovery actions paused awaiting operator authorization."
            icon={ShieldCheck}
          />
        )}
      </div>

      {/* Resolved Approvals Audit History */}
      {resolvedRuns.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl space-y-4">
          <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-500" />
            Operator Audit Decision History ({resolvedRuns.length})
          </h3>

          <div className="space-y-2.5 max-h-72 overflow-y-auto">
            {resolvedRuns.map((r) => (
              <div
                key={r.run_id}
                onClick={() => navigate(`/orchestration?run_id=${encodeURIComponent(r.run_id)}`)}
                className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-xs font-mono flex items-center justify-between cursor-pointer hover:border-slate-700 transition-all"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">{r.run_id}</span>
                    <StatusBadge status={r.approval_status || 'none'} size="sm" />
                  </div>
                  <div className="text-slate-400 text-[11px] mt-0.5">
                    Goal: &ldquo;{r.goal}&rdquo;
                  </div>
                </div>

                <div className="text-right text-[11px] text-slate-400">
                  <div>Decided by: <span className="text-white">{r.approver || 'operator'}</span></div>
                  <div>Outcome: <span className={r.status.includes('fail') ? 'text-rose-400' : 'text-emerald-400'}>{r.status}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Safety Confirmation Dialog */}
      <ConfirmationDialog
        isOpen={pendingAction !== null}
        title={
          pendingAction?.decision === 'approve'
            ? 'Confirm State-Changing Network Recovery'
            : 'Confirm Recommendation Rejection'
        }
        description={
          pendingAction?.decision === 'approve'
            ? `You are explicitly authorizing '${pendingAction?.actionType}' on target '${pendingAction?.target || pendingAction?.recId}'. Execution will resume to restore network state and verify reachability.`
            : `You are explicitly rejecting recommendation '${pendingAction?.recId}'. Execution will finalize without modifying the simulated network.`
        }
        confirmLabel={
          pendingAction?.decision === 'approve'
            ? 'Yes, Authorize Recovery'
            : 'Yes, Reject Mitigation'
        }
        confirmVariant={pendingAction?.decision === 'approve' ? 'primary' : 'danger'}
        isLoading={isSubmitting}
        onConfirm={handleDecision}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  );
};
