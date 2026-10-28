import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Flame,
  ShieldAlert,
} from 'lucide-react';
import { orchestrationApi } from '../api/orchestration';
import { simulationApi } from '../api/simulation';
import { eventsApi } from '../api/events';
import {
  NetworkEvent,
  SimulationSnapshot,
} from '../api/types';
import { ConfirmationDialog } from '../components/common/ConfirmationDialog';
import { EventTimeline } from '../components/events/EventTimeline';
import { LoadingState } from '../components/common/LoadingState';

export const RedAgentPage: React.FC = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [redEvents, setRedEvents] = useState<NetworkEvent[]>([]);

  // Simulation controls
  const [selectedScenario, setSelectedScenario] = useState<'link_disruption' | 'server_disruption'>('link_disruption');
  const [goal, setGoal] = useState('Evaluate failover routing upon primary link failure');
  const [useLlm, setUseLlm] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirmation modal
  const [showConfirm, setShowConfirm] = useState(false);

  const fetchRedState = useCallback(async () => {
    try {
      const [simData, eventsData] = await Promise.all([
        simulationApi.getState().catch(() => null),
        eventsApi.getEvents({ limit: 50 }).catch(() => []),
      ]);

      setSnapshot(simData);
      setRedEvents(
        eventsData.filter(
          (e) =>
            e.source === 'red_agent' ||
            e.event_type.includes('disruption') ||
            e.event_type.includes('scenario')
        )
      );
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch Red Agent state');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRedState();
  }, [fetchRedState]);

  const handleLaunchDisruption = async () => {
    setIsLaunching(true);
    setError(null);
    try {
      const run = await orchestrationApi.startRun({
        goal,
        scenario_id: selectedScenario,
        skip_disruption: false,
        use_llm: useLlm,
      });

      setShowConfirm(false);
      navigate(`/orchestration?run_id=${encodeURIComponent(run.run_id)}`);
    } catch (err: any) {
      setError(err.detail || err.message || 'Disruption launch failed');
      setShowConfirm(false);
    } finally {
      setIsLaunching(false);
    }
  };

  if (loading && !snapshot) {
    return <LoadingState message="Loading Red Agent Adversary Simulator..." />;
  }

  // Detect current disruption in simulation
  const targetLink = snapshot?.topology.links.find(
    (l) => {
      const pair = new Set([l.source, l.target]);
      return pair.has('router-1') && pair.has('server-1');
    }
  );
  const targetServer = snapshot?.topology.nodes.find((n) => n.id === 'server-1');

  const isLinkDisrupted = targetLink ? !targetLink.active : false;
  const isServerDisrupted = targetServer ? !targetServer.active : false;

  return (
    <div className="space-y-6">
      {/* Disclaimer Banner */}
      <div className="p-4 rounded-xl border border-rose-500/30 bg-rose-950/20 text-xs font-mono text-rose-300 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <div>
            <span className="font-bold uppercase tracking-wider block">
              Simulated Disruption Sandbox (Safe Environment)
            </span>
            <span className="text-slate-400 text-[11px]">
              All disruptions execute strictly inside the in-memory network topology simulator. No physical infrastructure is affected.
            </span>
          </div>
        </div>
        <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-rose-900/60 border border-rose-600 text-rose-200">
          Simulation Only
        </span>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Scenarios Configuration & Live Status Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Scenario Config & Launch Form */}
        <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl space-y-5">
          <div className="pb-3 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
              <Flame className="w-4 h-4 text-rose-400" />
              Red Agent Adversarial Disruption Launchpad
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Select an allowlisted fault scenario to inject into the live simulator.
            </p>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-2">
                Select Disruption Scenario
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div
                  onClick={() => {
                    setSelectedScenario('link_disruption');
                    setGoal('Evaluate failover routing upon primary link failure');
                  }}
                  className={`p-4 rounded-lg border cursor-pointer transition-all ${
                    selectedScenario === 'link_disruption'
                      ? 'border-rose-500 bg-rose-950/30 ring-1 ring-rose-400 shadow-[0_0_12px_rgba(239,68,68,0.2)]'
                      : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold font-mono text-white">
                      link_disruption
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      Link Cut
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Disables primary link between <span className="font-mono text-cyan-300">router-1</span> and <span className="font-mono text-cyan-300">server-1</span>. Tests redundant path failover through switch-1.
                  </p>
                </div>

                <div
                  onClick={() => {
                    setSelectedScenario('server_disruption');
                    setGoal('Analyze traffic flow reachability under application server failure');
                  }}
                  className={`p-4 rounded-lg border cursor-pointer transition-all ${
                    selectedScenario === 'server_disruption'
                      ? 'border-rose-500 bg-rose-950/30 ring-1 ring-rose-400 shadow-[0_0_12px_rgba(239,68,68,0.2)]'
                      : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold font-mono text-white">
                      server_disruption
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      Host Down
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Disables simulated host <span className="font-mono text-rose-300">server-1</span> (10.0.0.100). Measures impact on destination flows.
                  </p>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-1.5">
                Resilience Goal Specification
              </label>
              <input
                type="text"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                className="w-full px-3 py-2 text-xs font-mono rounded-md bg-slate-900 border border-slate-700 text-slate-100 focus:border-rose-500 focus:outline-none"
              />
            </div>

            <div className="pt-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useLlm}
                  onChange={(e) => setUseLlm(e.target.checked)}
                  className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-rose-500 focus:ring-0"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-slate-200">
                    Enable LLM Strategy Formulation (Qwen / Ollama)
                  </span>
                  <span className="text-[11px] text-slate-400">
                    Prompts Qwen to synthesize an evidence-grounded disruption rationale before execution.
                  </span>
                </div>
              </label>
            </div>

            <div className="pt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setShowConfirm(true)}
                disabled={isLaunching}
                className="px-5 py-2.5 rounded-md bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_0_15px_rgba(239,68,68,0.3)] transition-all disabled:opacity-50"
              >
                <Flame className="w-4 h-4" />
                Launch Disruption Simulation
              </button>
            </div>
          </div>
        </div>

        {/* Live Simulator Target Status */}
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-6 shadow-xl space-y-4">
          <div className="pb-3 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide">
              Target Entity Health State
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Live observational status in current simulator step.
            </p>
          </div>

          <div className="space-y-3 font-mono text-xs">
            {/* Link router-1 <-> server-1 */}
            <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-slate-300 font-semibold">router-1 &lt;-&gt; server-1</span>
                <span
                  className={`px-2 py-0.5 text-[10px] rounded font-bold uppercase ${
                    !isLinkDisrupted
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                  }`}
                >
                  {!isLinkDisrupted ? 'ACTIVE (UP)' : 'DISRUPTED (DOWN)'}
                </span>
              </div>
              <div className="text-[11px] text-slate-400">
                Primary data path to server-1 (latency: 3.0ms)
              </div>
            </div>

            {/* Host server-1 */}
            <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-slate-300 font-semibold">server-1 (10.0.0.100)</span>
                <span
                  className={`px-2 py-0.5 text-[10px] rounded font-bold uppercase ${
                    !isServerDisrupted
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                  }`}
                >
                  {!isServerDisrupted ? 'ACTIVE (HEALTHY)' : 'DISRUPTED (OFFLINE)'}
                </span>
              </div>
              <div className="text-[11px] text-slate-400">
                Core Application Server hosting TCP flow-1
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Red Agent Event Stream */}
      <EventTimeline
        events={redEvents}
        maxHeight="max-h-[350px]"
      />

      {/* Safety Confirmation Dialog */}
      <ConfirmationDialog
        isOpen={showConfirm}
        title="Confirm Simulated Fault Injection"
        description={`You are about to launch Red Agent disruption scenario '${selectedScenario}'. This will initiate an orchestration run, disable the simulated target entity, and test the network's failover and recovery behavior.`}
        confirmLabel="Yes, Inject Disruption"
        confirmVariant="danger"
        isLoading={isLaunching}
        onConfirm={handleLaunchDisruption}
        onCancel={() => setShowConfirm(false)}
      />
    </div>
  );
};
