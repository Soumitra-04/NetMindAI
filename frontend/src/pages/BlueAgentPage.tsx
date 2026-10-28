import React, { useEffect, useState, useCallback } from 'react';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Play,
  CheckCircle,
  XCircle,
  Cpu,
  Layers,
} from 'lucide-react';
import { blueApi } from '../api/blue';
import {
  ExecutionResult,
  RecoveryRecommendation,
  SentinelReport,
} from '../api/types';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingState } from '../components/common/LoadingState';
import { ConfirmationDialog } from '../components/common/ConfirmationDialog';

export const BlueAgentPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sentinel state
  const [sentinelReport, setSentinelReport] = useState<SentinelReport | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [useLlmDetection, setUseLlmDetection] = useState(false);

  // Recommendations state
  const [recommendations, setRecommendations] = useState<RecoveryRecommendation[]>([]);
  const [isRecommending, setIsRecommending] = useState(false);

  // Execution & Verification results
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // Confirmation state for approve / reject
  const [actionTarget, setActionTarget] = useState<{
    id: string;
    action: 'approve' | 'reject';
  } | null>(null);
  const [operatorNotes, setOperatorNotes] = useState('');
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);

  const fetchBlueData = useCallback(async () => {
    try {
      const recs = await blueApi.listRecommendations();
      setRecommendations(recs);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch recommendations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBlueData();
  }, [fetchBlueData]);

  const handleRunDetection = async () => {
    setIsDetecting(true);
    setError(null);
    try {
      const report = await blueApi.detect({ use_llm: useLlmDetection });
      setSentinelReport(report);
    } catch (err: any) {
      setError(err.detail || err.message || 'Detection failed');
    } finally {
      setIsDetecting(false);
    }
  };

  const handleFormulateRecommendation = async () => {
    setIsRecommending(true);
    setError(null);
    try {
      const rec = await blueApi.recommend({
        use_llm: useLlmDetection,
        detection_report: sentinelReport,
      });
      setRecommendations((prev) => [rec, ...prev.filter((r) => r.recommendation_id !== rec.recommendation_id)]);
    } catch (err: any) {
      setError(err.detail || err.message || 'Recommendation failed');
    } finally {
      setIsRecommending(false);
    }
  };

  const handleDecisionConfirm = async () => {
    if (!actionTarget) return;
    setIsSubmittingDecision(true);
    setError(null);
    try {
      if (actionTarget.action === 'approve') {
        const updated = await blueApi.approve(actionTarget.id, {
          approver: 'secops_lead',
          notes: operatorNotes,
        });
        setRecommendations((prev) =>
          prev.map((r) => (r.recommendation_id === updated.recommendation_id ? updated : r))
        );
      } else {
        const updated = await blueApi.reject(actionTarget.id, {
          approver: 'secops_lead',
          reason: operatorNotes,
        });
        setRecommendations((prev) =>
          prev.map((r) => (r.recommendation_id === updated.recommendation_id ? updated : r))
        );
      }
      setActionTarget(null);
      setOperatorNotes('');
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to submit decision');
    } finally {
      setIsSubmittingDecision(false);
    }
  };

  const handleExecute = async (recommendationId: string) => {
    setIsExecuting(true);
    setError(null);
    try {
      const result = await blueApi.execute(recommendationId);
      setExecutionResult(result);
      fetchBlueData();
    } catch (err: any) {
      setError(err.detail || err.message || 'Execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  if (loading && recommendations.length === 0) {
    return <LoadingState message="Loading Blue Sentinel &amp; Response Subsystems..." />;
  }

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div>
          <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-400" />
            Blue Sentinel Detection &amp; Response Workspace
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Independent observation, anomaly correlation, mitigation planning, and operational verification.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-mono text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={useLlmDetection}
              onChange={(e) => setUseLlmDetection(e.target.checked)}
              className="w-3.5 h-3.5 rounded bg-slate-900 border-slate-700 text-cyan-500"
            />
            <span>LLM Synthesis</span>
          </label>

          <button
            onClick={handleRunDetection}
            disabled={isDetecting}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono transition-colors disabled:opacity-50"
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            {isDetecting ? 'Inspecting...' : 'Run Sentinel Inspection'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Sentinel Detection Report Panel */}
      {sentinelReport ? (
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-white font-mono">
                Sentinel Inspection Report: {sentinelReport.detection_id}
              </h3>
              <StatusBadge status={sentinelReport.status} />
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-slate-400">Severity:</span>
              <StatusBadge status={sentinelReport.severity} variant="severity" size="sm" />
              <span className="text-slate-400">Confidence:</span>
              <span className="text-white font-bold">{(sentinelReport.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 uppercase block mb-1">Affected Links</span>
              <span className="text-slate-200">
                {sentinelReport.affected_links.join(', ') || 'None observed'}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 uppercase block mb-1">Affected Nodes</span>
              <span className="text-slate-200">
                {sentinelReport.affected_nodes.join(', ') || 'None observed'}
              </span>
            </div>
            <div className="p-3 rounded bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 uppercase block mb-1">Unreachable Flows</span>
              <span className="text-slate-200">
                {sentinelReport.affected_flows.join(', ') || 'None observed'}
              </span>
            </div>
          </div>

          {/* Human-readable Findings */}
          <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800 space-y-2">
            <span className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider block">
              Observed Anomalies &amp; Findings
            </span>
            <ul className="space-y-1.5 text-xs text-slate-300 font-mono">
              {sentinelReport.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-cyan-400">•</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Random Forest ML Model Diagnostic */}
          <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs font-mono flex items-start gap-3">
            <Cpu className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-slate-300 font-bold">Random Forest Model Status:</span>
                <span className="px-2 py-0.2 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[11px]">
                  {sentinelReport.model_inference.status}
                </span>
              </div>
              <p className="mt-1 text-slate-400 text-[11px] leading-relaxed">
                {sentinelReport.model_inference.reason ||
                  'Simulator operates at abstract graph layer; 67 CICIDS packet features are not fabricated.'}
              </p>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={handleFormulateRecommendation}
              disabled={isRecommending}
              className="px-4 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-semibold transition-colors disabled:opacity-50 inline-flex items-center gap-2 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
            >
              <ShieldCheck className="w-4 h-4" />
              {isRecommending ? 'Formulating...' : 'Formulate Recovery Recommendation'}
            </button>
          </div>
        </div>
      ) : (
        <div className="p-8 rounded-xl border border-slate-800 bg-[#0D1322] text-center space-y-3">
          <ShieldAlert className="w-8 h-8 text-slate-500 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300 font-mono">
            No Active Sentinel Inspection Captured
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto font-mono">
            Trigger an independent Sentinel inspection to scan observable node, link, and flow states.
          </p>
          <button
            onClick={handleRunDetection}
            disabled={isDetecting}
            className="px-4 py-2 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono transition-colors"
          >
            Scan Simulated Network Now
          </button>
        </div>
      )}

      {/* Execution Result Banner if executed */}
      {executionResult && (
        <div className="p-5 rounded-xl border border-emerald-500/40 bg-emerald-950/20 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-emerald-500/30">
            <span className="text-xs font-bold text-emerald-300 uppercase font-mono flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Recovery Execution &amp; Independent Verification Succeeded
            </span>
            <StatusBadge status={executionResult.verification.status} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono text-slate-300">
            <div>Action: <span className="text-white font-bold">{executionResult.action_type}</span></div>
            <div>Target: <span className="text-emerald-300">{executionResult.target}</span></div>
            <div>Reachable Flows: <span className="text-white font-bold">{executionResult.verification.reachable_flows}</span></div>
          </div>
        </div>
      )}

      {/* Formulated Recovery Recommendations Table */}
      <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl space-y-4">
        <div className="pb-3 border-b border-slate-800">
          <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            Formulated Recovery Recommendations &amp; Approvals
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Strict human approval required before executing any state-changing remediation.
          </p>
        </div>

        <div className="space-y-3">
          {recommendations.map((rec) => (
            <div
              key={rec.recommendation_id}
              className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 space-y-3 font-mono text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white">{rec.recommendation_id}</span>
                  <StatusBadge status={rec.approval_status} size="sm" />
                </div>
                <div className="text-slate-400 text-[11px]">
                  Created: {new Date(rec.created_at).toLocaleTimeString()}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-300">
                <div>
                  <span className="text-slate-500">Action: </span>
                  <span className="text-cyan-300 font-semibold">{rec.action_type}</span>
                </div>
                <div>
                  <span className="text-slate-500">Target Entity: </span>
                  <span className="text-amber-300 font-semibold">{rec.target || 'None'}</span>
                </div>
              </div>

              <p className="text-slate-300 text-xs leading-relaxed bg-black/30 p-2.5 rounded border border-slate-800">
                {rec.reason}
              </p>

              {/* Action Buttons depending on approval status */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                <div className="text-[11px] text-slate-400">
                  {rec.approver && (
                    <span>Decided by <span className="text-white">{rec.approver}</span></span>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  {rec.approval_status === 'pending' && (
                    <>
                      <button
                        onClick={() =>
                          setActionTarget({ id: rec.recommendation_id, action: 'reject' })
                        }
                        className="px-3 py-1 rounded bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-500/40 text-xs font-mono"
                      >
                        Reject
                      </button>
                      <button
                        onClick={() =>
                          setActionTarget({ id: rec.recommendation_id, action: 'approve' })
                        }
                        className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-medium shadow-[0_0_10px_rgba(16,185,129,0.25)]"
                      >
                        Approve
                      </button>
                    </>
                  )}

                  {rec.approval_status === 'approved' && (
                    <button
                      onClick={() => handleExecute(rec.recommendation_id)}
                      disabled={isExecuting}
                      className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-medium inline-flex items-center gap-1.5 shadow-[0_0_12px_rgba(6,182,212,0.3)] disabled:opacity-50"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Execute Approved Mitigation
                    </button>
                  )}

                  {rec.approval_status === 'executed' && (
                    <span className="text-emerald-400 flex items-center gap-1 text-[11px] font-bold">
                      <CheckCircle className="w-3.5 h-3.5" /> Executed &amp; Restored
                    </span>
                  )}

                  {rec.approval_status === 'rejected' && (
                    <span className="text-rose-400 flex items-center gap-1 text-[11px] font-bold">
                      <XCircle className="w-3.5 h-3.5" /> Operator Rejected
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {recommendations.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-500 font-mono italic">
              No recommendations formulated yet.
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Dialog for Approvals */}
      <ConfirmationDialog
        isOpen={actionTarget !== null}
        title={actionTarget?.action === 'approve' ? 'Approve Recovery Mitigation' : 'Reject Recovery Recommendation'}
        description={`Are you sure you want to ${actionTarget?.action} recommendation '${actionTarget?.id}'?`}
        confirmLabel={actionTarget?.action === 'approve' ? 'Yes, Authorize Action' : 'Yes, Reject Action'}
        confirmVariant={actionTarget?.action === 'approve' ? 'primary' : 'danger'}
        isLoading={isSubmittingDecision}
        onConfirm={handleDecisionConfirm}
        onCancel={() => setActionTarget(null)}
      />
    </div>
  );
};
