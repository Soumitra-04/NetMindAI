import React, { useState } from 'react';
import { X, Play } from 'lucide-react';
import { orchestrationApi } from '../../api/orchestration';
import { OrchestrationRunResponse } from '../../api/types';

interface CreateRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRunCreated?: (run: OrchestrationRunResponse) => void;
}

export const CreateRunModal: React.FC<CreateRunModalProps> = ({
  isOpen,
  onClose,
  onRunCreated,
}) => {
  const [goal, setGoal] = useState('Test network resilience under simulated disruption');
  const [scenarioId, setScenarioId] = useState<string>('link_disruption');
  const [skipDisruption, setSkipDisruption] = useState(false);
  const [useLlm, setUseLlm] = useState(false); // default false for quick deterministic runs or toggleable
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) {
      setError('Operational goal is required');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await orchestrationApi.startRun({
        goal: goal.trim(),
        scenario_id: skipDisruption ? undefined : scenarioId || undefined,
        skip_disruption: skipDisruption,
        use_llm: useLlm,
      });

      if (onRunCreated) {
        onRunCreated(response);
      }
      onClose();
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to start orchestration run');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="relative w-full max-w-lg rounded-xl border border-slate-700 bg-[#111827] p-6 shadow-2xl">
        <button
          onClick={onClose}
          disabled={isSubmitting}
          className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-800">
          <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Play className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">
              Launch Resilience Orchestration Run
            </h2>
            <p className="text-xs text-slate-400">
              Coordinates Red Agent disruption, Blue Sentinel detection, and recovery.
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wider font-mono">
              Operational Goal
            </label>
            <input
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
              placeholder="e.g. Verify failover routing upon primary link failure"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wider font-mono">
              Disruption Scenario
            </label>
            <select
              value={scenarioId}
              onChange={(e) => setScenarioId(e.target.value)}
              disabled={isSubmitting || skipDisruption}
              className="w-full px-3 py-2 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-100 focus:outline-none focus:border-cyan-500 font-mono disabled:opacity-40"
            >
              <option value="link_disruption">
                link_disruption (Disable router-1 &lt;-&gt; server-1 link)
              </option>
              <option value="server_disruption">
                server_disruption (Disable server-1 host)
              </option>
              <option value="">
                Auto-select via Red Agent (LLM planning)
              </option>
            </select>
          </div>

          <div className="pt-2 space-y-3 border-t border-slate-800">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={skipDisruption}
                onChange={(e) => setSkipDisruption(e.target.checked)}
                disabled={isSubmitting}
                className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0"
              />
              <div className="flex flex-col">
                <span className="text-xs font-medium text-slate-200">
                  Skip Disruption (Baseline Assessment)
                </span>
                <span className="text-[11px] text-slate-400">
                  Evaluates a healthy network without injecting Red Agent faults.
                </span>
              </div>
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                disabled={isSubmitting}
                className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0"
              />
              <div className="flex flex-col">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-200">
                    Enable LLM Reasoning (Ollama / Qwen)
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-violet-950 text-violet-300 border border-violet-800 font-mono">
                    Ollama
                  </span>
                </div>
                <span className="text-[11px] text-slate-400">
                  When disabled, agents run high-speed deterministic heuristics.
                </span>
              </div>
            </label>
          </div>

          <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-2 text-xs font-medium rounded-md border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium rounded-md bg-cyan-600 hover:bg-cyan-500 text-white transition-colors disabled:opacity-50 inline-flex items-center gap-2 shadow-[0_0_12px_rgba(6,182,212,0.3)]"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Initiating Run...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  Execute Workflow
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
