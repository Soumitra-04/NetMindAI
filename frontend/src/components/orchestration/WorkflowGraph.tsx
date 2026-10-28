import React from 'react';
import {
  CheckCircle2,
  Clock,
  PlayCircle,
  UserCheck,
  XCircle,
  FastForward,
} from 'lucide-react';
import { OrchestrationRunResponse, OrchestrationStage } from '../../api/types';

interface WorkflowGraphProps {
  run: OrchestrationRunResponse;
}

interface StageDefinition {
  id: OrchestrationStage;
  label: string;
  category: 'setup' | 'red' | 'blue' | 'gate' | 'recovery' | 'teardown';
  description: string;
}

const STAGES: StageDefinition[] = [
  {
    id: 'initialized',
    label: '1. Init Run',
    category: 'setup',
    description: 'Validate run goal, startup state & record baseline telemetry',
  },
  {
    id: 'plan_disruption',
    label: '2. Plan Disruption',
    category: 'red',
    description: 'Red Agent LLM / scenario selection',
  },
  {
    id: 'execute_disruption',
    label: '3. Execute Disruption',
    category: 'red',
    description: 'Inject fault into simulated network topology',
  },
  {
    id: 'detect_anomaly',
    label: '4. Detect Anomaly',
    category: 'blue',
    description: 'Blue Sentinel independent topology & telemetry inspection',
  },
  {
    id: 'evaluate_detection',
    label: '5. Evaluate Detection',
    category: 'blue',
    description: 'Analyze findings to determine if mitigation is required',
  },
  {
    id: 'recommend_recovery',
    label: '6. Recommend Recovery',
    category: 'blue',
    description: 'Formulate evidence-grounded remediation plan',
  },
  {
    id: 'validate_recommendation',
    label: '7. Validate Rec.',
    category: 'blue',
    description: 'Validate proposed action preconditions against simulator',
  },
  {
    id: 'request_human_approval',
    label: '8. Operator Approval',
    category: 'gate',
    description: 'LangGraph Interrupt() gate requiring human decision',
  },
  {
    id: 'execute_recovery',
    label: '9. Execute Recovery',
    category: 'recovery',
    description: 'Apply approved remediation to restore network state',
  },
  {
    id: 'verify_recovery',
    label: '10. Verify Recovery',
    category: 'recovery',
    description: 'Independent verification of link/node status & flow reachability',
  },
  {
    id: 'finalize_run',
    label: '11. Finalize Run',
    category: 'teardown',
    description: 'Record completion metrics and finalize audit records',
  },
];

export const WorkflowGraph: React.FC<WorkflowGraphProps> = ({ run }) => {
  const currentStage = run.stage;
  const currentStatus = run.status;
  const failureStage = run.failure_stage;

  // Determine stage execution state
  const getStageStatus = (
    stageId: OrchestrationStage,
    index: number
  ): 'completed' | 'active' | 'waiting_approval' | 'failed' | 'skipped' | 'pending' => {
    // 1. Check for failure at this stage
    if (failureStage === stageId || (currentStatus === 'failed' && currentStage === stageId)) {
      return 'failed';
    }

    // 2. Check for human approval gate
    if (stageId === 'request_human_approval' && run.pending_approval) {
      return 'waiting_approval';
    }

    // 3. Check if skipped based on run configuration
    if (run.skip_disruption && (stageId === 'plan_disruption' || stageId === 'execute_disruption')) {
      return 'skipped';
    }
    if (run.scenario_id && stageId === 'plan_disruption') {
      return 'skipped'; // Scenario was provided upfront, plan_disruption was bypassed
    }

    // If network was healthy or evaluate decided no mitigation needed:
    if (
      (currentStatus === 'completed_healthy' || currentStatus === 'completed_no_action') &&
      index >= 5 &&
      index <= 9
    ) {
      return 'skipped';
    }

    // If operator rejected recommendation:
    if (
      (currentStatus === 'rejected' || run.approval_status === 'rejected') &&
      (stageId === 'execute_recovery' || stageId === 'verify_recovery')
    ) {
      return 'skipped';
    }

    // 4. Find index of current stage
    const currentStageIndex = STAGES.findIndex((s) => s.id === currentStage);

    if (currentStage === 'completed') {
      return 'completed';
    }

    if (stageId === currentStage) {
      if (run.pending_approval) return 'waiting_approval';
      if (currentStatus === 'running') return 'active';
      if (currentStatus === 'failed') return 'failed';
      return 'active';
    }

    if (currentStageIndex > index) {
      return 'completed';
    }

    return 'pending';
  };

  const renderIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
      case 'active':
        return <PlayCircle className="w-4 h-4 text-cyan-400 animate-pulse" />;
      case 'waiting_approval':
        return <UserCheck className="w-4 h-4 text-amber-400 animate-bounce" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-rose-400" />;
      case 'skipped':
        return <FastForward className="w-4 h-4 text-slate-500" />;
      default:
        return <Clock className="w-4 h-4 text-slate-600" />;
    }
  };

  const getStageCardStyle = (status: string, isCurrent: boolean) => {
    let base = 'p-3 rounded-lg border transition-all text-left relative flex flex-col justify-between ';
    if (isCurrent) {
      base += 'ring-1 ring-cyan-400 ';
    }
    if (status === 'active') {
      base += 'bg-cyan-950/40 border-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.3)] ring-1 ring-cyan-400';
    } else if (status === 'waiting_approval') {
      base += 'bg-amber-950/40 border-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.3)] ring-1 ring-amber-400';
    } else if (status === 'failed') {
      base += 'bg-rose-950/40 border-rose-500 shadow-[0_0_15px_rgba(239,68,68,0.3)]';
    } else if (status === 'completed') {
      base += 'bg-emerald-950/20 border-emerald-500/40 hover:border-emerald-500/60';
    } else if (status === 'skipped') {
      base += 'bg-slate-900/40 border-slate-800/80 opacity-50 border-dashed';
    } else {
      base += 'bg-[#111827] border-slate-800 text-slate-400 opacity-70';
    }
    return base;
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div>
          <h2 className="text-sm font-semibold text-white tracking-wide flex items-center gap-2">
            LangGraph Execution Graph
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              Active Topology
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time conditional routing based on checkpointed graph state.
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> Done
          </span>
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" /> Running
          </span>
          <span className="flex items-center gap-1.5 text-amber-400">
            <span className="w-2 h-2 rounded-full bg-amber-400" /> Awaiting Operator
          </span>
          <span className="flex items-center gap-1.5 text-rose-400">
            <span className="w-2 h-2 rounded-full bg-rose-400" /> Failed
          </span>
          <span className="flex items-center gap-1.5 text-slate-500">
            <span className="w-2 h-2 rounded-full bg-slate-600" /> Skipped
          </span>
        </div>
      </div>

      {/* Grid of Nodes with Directional Connectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
        {STAGES.map((stage, idx) => {
          const status = getStageStatus(stage.id, idx);
          const isCurrent = run.stage === stage.id;

          return (
            <div
              key={stage.id}
              className={getStageCardStyle(status, isCurrent)}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-mono font-bold tracking-wider text-slate-200 uppercase">
                  {stage.label}
                </span>
                {renderIcon(status)}
              </div>

              <p className="text-[10px] text-slate-400 line-clamp-2 leading-relaxed mb-3">
                {stage.description}
              </p>

              <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono">
                <span className="text-slate-500 uppercase">{stage.category}</span>
                <span
                  className={`font-semibold capitalize ${
                    status === 'completed'
                      ? 'text-emerald-400'
                      : status === 'active'
                      ? 'text-cyan-400'
                      : status === 'waiting_approval'
                      ? 'text-amber-400'
                      : status === 'failed'
                      ? 'text-rose-400'
                      : status === 'skipped'
                      ? 'text-slate-500'
                      : 'text-slate-600'
                  }`}
                >
                  {status.replace('_', ' ')}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Conditional routing summary */}
      <div className="mt-4 p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs font-mono flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-slate-300">
          <span className="text-cyan-400 font-bold">Routing Context:</span>
          <span>
            {run.skip_disruption
              ? 'Bypassed Red Disruption -> Direct Baseline Sentinel Check'
              : run.scenario_id
              ? `Scenario Override: ${run.scenario_id} -> Disruption Execution`
              : 'Red Agent Autonomous Planning'}
          </span>
        </div>
        <div className="text-slate-400">
          Approval Gate: <span className="text-white">{run.pending_approval ? 'HALTED (Operator Gate Active)' : run.approval_status || 'Auto'}</span>
        </div>
      </div>
    </div>
  );
};
