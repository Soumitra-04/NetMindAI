import React, { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  User,
  FileText,
  Lock,
} from 'lucide-react';
import { orchestrationApi } from '../../api/orchestration';
import { OrchestrationRunResponse } from '../../api/types';
import { ConfirmationDialog } from '../common/ConfirmationDialog';

interface ApprovalPanelProps {
  run: OrchestrationRunResponse;
  onDecisionSubmitted: (updatedRun: OrchestrationRunResponse) => void;
}

export const ApprovalPanel: React.FC<ApprovalPanelProps> = ({
  run,
  onDecisionSubmitted,
}) => {
  const [approver, setApprover] = useState('secops_lead');
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirmation dialog state
  const [pendingDecision, setPendingDecision] = useState<'approve' | 'reject' | null>(null);

  const recommendation = run.recommendation;
  const recId = run.recommendation_id || recommendation?.recommendation_id;

  if (!run.pending_approval || !recId) {
    return null;
  }

  const handleDecision = async () => {
    if (!pendingDecision) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const updatedRun = await orchestrationApi.resumeRun(run.run_id, {
        decision: pendingDecision,
        recommendation_id: recId,
        approver: approver.trim() || 'operator',
        notes: notes.trim(),
      });

      setPendingDecision(null);
      onDecisionSubmitted(updatedRun);
    } catch (err: any) {
      setError(err.detail || err.message || `Failed to submit ${pendingDecision} decision.`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-6 shadow-[0_0_20px_rgba(245,158,11,0.15)] my-6">
      <div className="flex items-start justify-between pb-4 border-b border-amber-500/30">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 animate-pulse">
            <Lock className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-amber-200">
                Operator Approval Gate Paused Execution
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-900/60 text-amber-300 border border-amber-600 font-semibold uppercase">
                Human-in-the-Loop Active
              </span>
            </div>
            <p className="text-xs text-amber-300/80 mt-1">
              State-changing network recovery action proposed by Blue Response requires operator verification and explicit authorization.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-4 p-3 rounded bg-rose-950/60 border border-rose-500/50 text-rose-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Recommendation Details */}
      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 rounded-lg bg-[#0D1322] border border-slate-800">
          <span className="text-[10px] font-mono font-semibold text-slate-400 uppercase tracking-wider block mb-1">
            Proposed Action
          </span>
          <div className="text-sm font-bold font-mono text-cyan-300">
            {recommendation?.action_type || 'N/A'}
          </div>
          <div className="mt-2 text-xs text-slate-300">
            <span className="text-slate-500 font-mono">Target: </span>
            <span className="font-mono text-amber-300 font-semibold">
              {recommendation?.target || 'All affected entities'}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-300">
            <span className="text-slate-500 font-mono">Recommendation ID: </span>
            <span className="font-mono text-slate-400">{recId}</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0D1322] border border-slate-800">
          <span className="text-[10px] font-mono font-semibold text-slate-400 uppercase tracking-wider block mb-1">
            Expected Operational Effect & Validation
          </span>
          <p className="text-xs text-slate-200 leading-relaxed">
            {recommendation?.expected_effect || 'Restores network link/node availability to recover reachable traffic flows.'}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" /> Preconditions Verified
            </span>
          </div>
        </div>
      </div>

      {/* Reason / Rationale */}
      {recommendation?.reason && (
        <div className="mt-4 p-3 rounded-lg bg-[#0D1322] border border-slate-800">
          <span className="text-[10px] font-mono font-semibold text-slate-400 uppercase tracking-wider block mb-1">
            Mitigation Rationale
          </span>
          <p className="text-xs text-slate-300 leading-relaxed font-mono">
            {recommendation.reason}
          </p>
        </div>
      )}

      {/* Operator Decision Form */}
      <div className="mt-5 pt-4 border-t border-amber-500/20 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-mono text-slate-300 mb-1 flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-slate-400" />
            Operator Identity
          </label>
          <input
            type="text"
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            disabled={isSubmitting}
            placeholder="e.g. secops_lead, noc_engineer"
            className="w-full px-3 py-2 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-100 font-mono focus:border-amber-400 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-mono text-slate-300 mb-1 flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-slate-400" />
            Decision Notes / Audit Log
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isSubmitting}
            placeholder="Optional justification or policy citation"
            className="w-full px-3 py-2 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-100 font-mono focus:border-amber-400 focus:outline-none"
          />
        </div>
      </div>

      {/* Explicit Actions (Require Confirmation) */}
      <div className="mt-6 flex items-center justify-end gap-4">
        <button
          type="button"
          onClick={() => setPendingDecision('reject')}
          disabled={isSubmitting}
          className="px-4 py-2 rounded-md border border-rose-500/40 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 text-xs font-semibold inline-flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          <XCircle className="w-4 h-4 text-rose-400" />
          Reject Recommendation
        </button>

        <button
          type="button"
          onClick={() => setPendingDecision('approve')}
          disabled={isSubmitting}
          className="px-5 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all disabled:opacity-50"
        >
          <CheckCircle className="w-4 h-4" />
          Approve & Execute Recovery
        </button>
      </div>

      {/* Safety Confirmation Dialog */}
      <ConfirmationDialog
        isOpen={pendingDecision !== null}
        title={
          pendingDecision === 'approve'
            ? 'Confirm Recovery Authorization'
            : 'Confirm Recommendation Rejection'
        }
        description={
          pendingDecision === 'approve'
            ? `Are you sure you want to authorize execution of '${recommendation?.action_type}' targeting '${recommendation?.target || recId}'? This will resume LangGraph execution and modify the simulated network state.`
            : `Are you sure you want to reject recommendation '${recId}'? Execution will resume directly to finalize_run and mark the run as REJECTED without modifying network state.`
        }
        confirmLabel={
          pendingDecision === 'approve' ? 'Yes, Authorize Recovery' : 'Yes, Reject Mitigation'
        }
        confirmVariant={pendingDecision === 'approve' ? 'primary' : 'danger'}
        isLoading={isSubmitting}
        onConfirm={handleDecision}
        onCancel={() => setPendingDecision(null)}
      />
    </div>
  );
};
