import React, { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Flame,
  ShieldAlert,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { OrchestrationRunResponse } from '../../api/types';
import { StatusBadge } from '../common/StatusBadge';

interface RunStatusPanelProps {
  run: OrchestrationRunResponse;
}

export const RunStatusPanel: React.FC<RunStatusPanelProps> = ({ run }) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'red' | 'blue' | 'recovery' | 'raw'>('overview');
  const [copied, setCopied] = useState(false);

  const copyRunId = () => {
    navigator.clipboard.writeText(run.run_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return `${d.toLocaleTimeString()} (${d.toLocaleDateString()})`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0D1322] overflow-hidden shadow-xl mt-6">
      {/* Header bar */}
      <div className="p-5 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 bg-slate-900/40">
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-slate-400">Run ID:</span>
              <span className="text-sm font-bold font-mono text-white tracking-wide">
                {run.run_id}
              </span>
              <button
                onClick={copyRunId}
                title="Copy Run ID"
                className="text-slate-500 hover:text-slate-300 transition-colors p-1"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
              {copied && <span className="text-[10px] text-emerald-400 font-mono">Copied</span>}
            </div>
            <span className="text-xs text-slate-300 font-mono mt-0.5">
              Goal: &ldquo;{run.goal}&rdquo;
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-500">Stage:</span>
            <StatusBadge status={run.stage} variant="stage" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-500">Status:</span>
            <StatusBadge status={run.status} variant="status" />
          </div>
        </div>
      </div>

      {/* Failure banner if failed */}
      {run.error && (
        <div className="p-4 bg-rose-950/40 border-b border-rose-500/30 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-bold text-rose-300 uppercase font-mono tracking-wider">
              Failure Recorded at Stage: {run.failure_stage || run.stage}
            </div>
            <div className="text-xs text-rose-200 font-mono mt-1 leading-relaxed bg-black/40 p-2.5 rounded border border-rose-900/40">
              {run.error}
            </div>
          </div>
        </div>
      )}

      {/* Nav Tabs */}
      <div className="flex items-center border-b border-slate-800 bg-[#0B0F19] px-4 gap-2 text-xs font-mono">
        <button
          onClick={() => setActiveTab('overview')}
          className={`py-3 px-3 border-b-2 font-medium transition-all flex items-center gap-2 ${
            activeTab === 'overview'
              ? 'border-cyan-400 text-cyan-300 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-3.5 h-3.5" /> Overview
        </button>
        <button
          onClick={() => setActiveTab('red')}
          className={`py-3 px-3 border-b-2 font-medium transition-all flex items-center gap-2 ${
            activeTab === 'red'
              ? 'border-rose-400 text-rose-300 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Flame className="w-3.5 h-3.5" /> Red Agent Disruption
        </button>
        <button
          onClick={() => setActiveTab('blue')}
          className={`py-3 px-3 border-b-2 font-medium transition-all flex items-center gap-2 ${
            activeTab === 'blue'
              ? 'border-cyan-400 text-cyan-300 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" /> Blue Sentinel Detection
        </button>
        <button
          onClick={() => setActiveTab('recovery')}
          className={`py-3 px-3 border-b-2 font-medium transition-all flex items-center gap-2 ${
            activeTab === 'recovery'
              ? 'border-emerald-400 text-emerald-300 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5" /> Recovery &amp; Verification
        </button>
        <button
          onClick={() => setActiveTab('raw')}
          className={`py-3 px-3 border-b-2 font-medium transition-all flex items-center gap-2 ${
            activeTab === 'raw'
              ? 'border-violet-400 text-violet-300 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Terminal className="w-3.5 h-3.5" /> State Payload (JSON)
        </button>
      </div>

      {/* Tab Contents */}
      <div className="p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Metadata Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                <span className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  Created At
                </span>
                <span className="text-xs font-mono text-slate-200">
                  {formatDate(run.created_at)}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                <span className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  Last Updated
                </span>
                <span className="text-xs font-mono text-slate-200">
                  {formatDate(run.updated_at)}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                <span className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  Completed At
                </span>
                <span className="text-xs font-mono text-slate-200">
                  {formatDate(run.completed_at)}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                <span className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  Approval Status
                </span>
                <span className="text-xs font-mono font-semibold text-slate-200">
                  {run.approval_status ? (
                    <StatusBadge status={run.approval_status} size="sm" />
                  ) : (
                    'Not required / None'
                  )}
                </span>
              </div>
            </div>

            {/* Quick Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Red Summary */}
              <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800">
                <div className="flex items-center gap-2 mb-2 text-rose-400 font-semibold text-xs uppercase font-mono">
                  <Flame className="w-4 h-4" /> Disruption Injected
                </div>
                {run.disruption_result ? (
                  <div className="text-xs font-mono space-y-1 text-slate-300">
                    <div>Scenario: <span className="text-white">{run.disruption_result.scenario_id}</span></div>
                    <div>Target: <span className="text-rose-300 font-bold">{run.disruption_result.target}</span></div>
                    <div>Action: <span className="text-slate-400">{run.disruption_result.action}</span></div>
                  </div>
                ) : run.skip_disruption ? (
                  <div className="text-xs text-slate-500 italic">Disruption intentionally skipped.</div>
                ) : (
                  <div className="text-xs text-slate-500 italic">No disruption executed yet.</div>
                )}
              </div>

              {/* Blue Sentinel Summary */}
              <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800">
                <div className="flex items-center gap-2 mb-2 text-cyan-400 font-semibold text-xs uppercase font-mono">
                  <ShieldAlert className="w-4 h-4" /> Sentinel Detection
                </div>
                {run.sentinel_report ? (
                  <div className="text-xs font-mono space-y-1 text-slate-300">
                    <div>Status: <StatusBadge status={run.sentinel_report.status} size="sm" /></div>
                    <div>Affected Links: <span className="text-white">{run.sentinel_report.affected_links.join(', ') || 'None'}</span></div>
                    <div>Affected Nodes: <span className="text-white">{run.sentinel_report.affected_nodes.join(', ') || 'None'}</span></div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 italic">Detection pending or not reached.</div>
                )}
              </div>

              {/* Recovery Summary */}
              <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800">
                <div className="flex items-center gap-2 mb-2 text-emerald-400 font-semibold text-xs uppercase font-mono">
                  <ShieldCheck className="w-4 h-4" /> Verification Result
                </div>
                {run.verification_report ? (
                  <div className="text-xs font-mono space-y-1 text-slate-300">
                    <div>Verification: <StatusBadge status={run.verification_report.status} size="sm" /></div>
                    <div>Target Active: <span className={run.verification_report.target_active ? 'text-emerald-400' : 'text-rose-400'}>{String(run.verification_report.target_active)}</span></div>
                    <div>Reachable Flows: <span className="text-white font-bold">{run.verification_report.reachable_flows}</span></div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 italic">Verification pending recovery execution.</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'red' && (
          <div className="space-y-4">
            <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider">
              Red Agent Disruption Planning &amp; Execution
            </h3>
            {run.red_plan && (
              <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 font-mono text-xs space-y-2">
                <div className="text-cyan-400 font-semibold">Formulated Plan:</div>
                <div className="text-slate-300">Planner: <span className="text-white">{run.red_plan.planner_model || 'heuristic'}</span></div>
                <div className="text-slate-300">Scenario Selected: <span className="text-rose-400 font-bold">{run.red_plan.scenario_id}</span></div>
                <div className="text-slate-400 italic bg-black/30 p-2.5 rounded border border-slate-800">
                  Rationale: &ldquo;{run.red_plan.rationale}&rdquo;
                </div>
              </div>
            )}
            {run.disruption_result ? (
              <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 font-mono text-xs space-y-2">
                <div className="text-rose-400 font-semibold">Execution Telemetry:</div>
                <div>Action: <span className="text-white">{run.disruption_result.action}</span></div>
                <div>Target ID: <span className="text-rose-300 font-bold">{run.disruption_result.target}</span></div>
                <div>Route Before: <span className="text-slate-400">{JSON.stringify(run.disruption_result.route_before)}</span></div>
                <div>Route After: <span className="text-slate-400">{JSON.stringify(run.disruption_result.route_after)}</span></div>
                <div>Disruption Status: <span className="text-rose-400 font-bold">Active in Simulator</span></div>
              </div>
            ) : run.skip_disruption ? (
              <div className="p-4 text-xs font-mono text-slate-400 bg-slate-900/40 rounded-lg border border-slate-800">
                Red Disruption was disabled for this run (Baseline observation mode).
              </div>
            ) : (
              <div className="p-4 text-xs font-mono text-slate-500 bg-slate-900/40 rounded-lg border border-slate-800">
                Disruption execution stage has not completed yet.
              </div>
            )}
          </div>
        )}

        {activeTab === 'blue' && (
          <div className="space-y-4">
            <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider">
              Blue Sentinel Autonomous Detection
            </h3>
            {run.sentinel_report ? (
              <div className="space-y-4">
                <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-xs font-mono space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-cyan-400 font-semibold">Detection ID: {run.sentinel_report.detection_id}</span>
                    <StatusBadge status={run.sentinel_report.status} />
                  </div>
                  <div>Severity: <StatusBadge status={run.sentinel_report.severity} variant="severity" size="sm" /></div>
                  <div>Confidence: <span className="text-white">{(run.sentinel_report.confidence * 100).toFixed(0)}%</span></div>
                  <div>Recommended Action: <span className="text-cyan-300">{run.sentinel_report.recommended_action}</span></div>
                </div>

                {/* Findings */}
                {run.sentinel_report.findings.length > 0 && (
                  <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800">
                    <span className="text-xs font-mono text-slate-400 font-semibold uppercase block mb-2">
                      Specific Findings
                    </span>
                    <ul className="space-y-1.5 text-xs text-slate-300 font-mono">
                      {run.sentinel_report.findings.map((finding, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-amber-400">•</span>
                          <span>{finding}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* ML Inference Status */}
                <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-xs font-mono">
                  <span className="text-slate-400 font-semibold uppercase block mb-1">
                    Random Forest Intrusion Model Status
                  </span>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-slate-400">Status:</span>
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      {run.sentinel_report.model_inference.status}
                    </span>
                  </div>
                  {run.sentinel_report.model_inference.reason && (
                    <p className="mt-2 text-slate-400 italic text-[11px]">
                      {run.sentinel_report.model_inference.reason}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="p-4 text-xs font-mono text-slate-500 bg-slate-900/40 rounded-lg border border-slate-800">
                No Sentinel report captured for this run yet.
              </div>
            )}
          </div>
        )}

        {activeTab === 'recovery' && (
          <div className="space-y-4">
            <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider">
              Mitigation Execution &amp; Verification
            </h3>

            {/* Recommendation info */}
            {run.recommendation && (
              <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 font-mono text-xs space-y-2">
                <div className="text-cyan-400 font-semibold">Formulated Recommendation:</div>
                <div>Action: <span className="text-white font-bold">{run.recommendation.action_type}</span></div>
                <div>Target: <span className="text-amber-300">{run.recommendation.target || 'N/A'}</span></div>
                <div className="text-slate-300">Expected Effect: {run.recommendation.expected_effect}</div>
                {run.recommendation.approval_notes && (
                  <div className="text-slate-400 italic mt-2">
                    Approver Notes ({run.recommendation.approver}): &ldquo;{run.recommendation.approval_notes}&rdquo;
                  </div>
                )}
              </div>
            )}

            {/* Verification Report */}
            {run.verification_report ? (
              <div className="p-4 rounded-lg bg-emerald-950/20 border border-emerald-500/30 font-mono text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-emerald-400 font-bold flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4" /> Independent Post-Recovery Verification Report
                  </span>
                  <StatusBadge status={run.verification_report.status} />
                </div>
                <div>Target Entity Restored: <span className="text-white font-bold">{String(run.verification_report.target_active)}</span></div>
                <div>Verified Shortest Path: <span className="text-cyan-300">{JSON.stringify(run.verification_report.route_after)}</span></div>
                <div>Active Reachable Flows: <span className="text-white font-bold">{run.verification_report.reachable_flows}</span></div>
              </div>
            ) : (
              <div className="p-4 text-xs font-mono text-slate-500 bg-slate-900/40 rounded-lg border border-slate-800">
                Recovery execution has not occurred.
              </div>
            )}
          </div>
        )}

        {activeTab === 'raw' && (
          <div className="relative">
            <pre className="p-4 rounded-lg bg-[#080C14] border border-slate-800 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-96 leading-relaxed">
              {JSON.stringify(run, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
