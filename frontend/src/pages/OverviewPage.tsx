import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  CheckCircle2,
  GitBranch,
  Network,
  ShieldAlert,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { orchestrationApi } from '../api/orchestration';
import { simulationApi } from '../api/simulation';
import { eventsApi } from '../api/events';
import {
  NetworkEvent,
  OrchestrationRunResponse,
  SimulationSnapshot,
} from '../api/types';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [simState, setSimState] = useState<SimulationSnapshot | null>(null);
  const [runs, setRuns] = useState<OrchestrationRunResponse[]>([]);
  const [recentEvents, setRecentEvents] = useState<NetworkEvent[]>([]);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [simData, runsData, eventsData] = await Promise.all([
        simulationApi.getState().catch(() => null),
        orchestrationApi.listRuns().catch(() => []),
        eventsApi.getEvents({ limit: 15 }).catch(() => []),
      ]);

      setSimState(simData);
      setRuns(runsData);
      setRecentEvents(eventsData);
    } catch (err: any) {
      setError(err.message || 'Failed to load NOC dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  if (loading) {
    return <LoadingState message="Connecting to NOC Telemetry &amp; Orchestration..." />;
  }

  if (error && !simState && runs.length === 0) {
    return (
      <ErrorState
        title="NOC Telemetry Feed Offline"
        message={error}
        onRetry={loadDashboardData}
      />
    );
  }

  // Calculate real metrics from existing data
  const totalNodes = simState?.topology.nodes.length ?? 'Unavailable';
  const activeNodes = simState?.topology.nodes.filter((n) => n.active).length ?? 'Unavailable';
  const totalLinks = simState?.topology.links.length ?? 'Unavailable';
  const activeLinks = simState?.topology.links.filter((l) => l.active).length ?? 'Unavailable';

  const pendingApprovals = runs.filter((r) => r.pending_approval || r.status === 'pending_approval');
  const activeRuns = runs.filter((r) => r.status === 'running');
  const completedRuns = runs.filter((r) =>
    ['completed', 'completed_healthy', 'completed_no_action'].includes(r.status)
  );

  // Real traffic flows data for chart
  const flowChartData = (simState?.flows || []).map((flow) => ({
    name: flow.id,
    route: `${flow.source} -> ${flow.destination}`,
    latency: flow.path_latency_ms ?? 0,
    offered: flow.offered_mbps,
    reachable: flow.reachable ? 1 : 0,
  }));

  // Events distribution by severity
  const severityCounts: Record<string, number> = { info: 0, warning: 0, critical: 0, error: 0 };
  recentEvents.forEach((evt) => {
    const sev = (evt.severity || 'info').toLowerCase();
    if (severityCounts[sev] !== undefined) {
      severityCounts[sev]++;
    } else {
      severityCounts[sev] = 1;
    }
  });

  const severityChartData = [
    { name: 'Info', count: severityCounts.info || 0, color: '#06B6D4' },
    { name: 'Warning', count: severityCounts.warning || 0, color: '#F59E0B' },
    { name: 'Error / Critical', count: (severityCounts.error || 0) + (severityCounts.critical || 0), color: '#EF4444' },
  ];

  return (
    <div className="space-y-6">
      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Network Node Health"
          value={
            typeof activeNodes === 'number'
              ? `${activeNodes} / ${totalNodes}`
              : 'Unavailable'
          }
          subtitle={
            typeof activeLinks === 'number'
              ? `${activeLinks} / ${totalLinks} active links`
              : 'Telemetry not loaded'
          }
          icon={Network}
          variant={typeof activeNodes === 'number' && activeNodes === totalNodes ? 'emerald' : 'amber'}
          badge={typeof activeNodes === 'number' && activeNodes === totalNodes ? 'Nominal' : 'Disrupted'}
        />

        <MetricCard
          title="Active Resilience Runs"
          value={activeRuns.length}
          subtitle={`${runs.length} total runs recorded`}
          icon={GitBranch}
          variant="cyan"
        />

        <MetricCard
          title="Pending Approvals"
          value={pendingApprovals.length}
          subtitle={
            pendingApprovals.length > 0
              ? 'Human approval gate paused'
              : 'All gates resolved'
          }
          icon={ShieldAlert}
          variant={pendingApprovals.length > 0 ? 'amber' : 'default'}
          badge={pendingApprovals.length > 0 ? 'Action Required' : 'Clear'}
        />

        <MetricCard
          title="Autonomous Recoveries"
          value={completedRuns.length}
          subtitle="Validated operational verifications"
          icon={CheckCircle2}
          variant="emerald"
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Real Flow Latencies & Load */}
        <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl">
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-800">
            <div>
              <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide">
                Live Traffic Flows — Shortest Path Latency (ms)
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Real path calculations via Dijkstra&apos;s algorithm on active topology.
              </p>
            </div>
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800">
              {simState?.metrics.traffic.total_flows ?? 0} Registered Flows
            </span>
          </div>

          <div className="h-60 w-full">
            {flowChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flowChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                  <XAxis
                    dataKey="name"
                    stroke="#64748B"
                    fontSize={11}
                    fontFamily="ui-monospace, monospace"
                  />
                  <YAxis stroke="#64748B" fontSize={11} fontFamily="ui-monospace, monospace" unit="ms" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      borderColor: '#374151',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontFamily: 'ui-monospace, monospace',
                    }}
                    labelStyle={{ color: '#38BDF8', fontWeight: 600 }}
                  />
                  <Bar dataKey="latency" name="Latency (ms)" fill="#06B6D4" radius={[4, 4, 0, 0]}>
                    {flowChartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.reachable ? '#06B6D4' : '#EF4444'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-xs text-slate-500 font-mono">
                No active traffic flows found.
              </div>
            )}
          </div>
        </div>

        {/* Real Event Severities */}
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl">
          <div className="pb-3 mb-4 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide">
              Recent Events Breakdown
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Live telemetry distribution from last {recentEvents.length} events.
            </p>
          </div>

          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={severityChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="name" stroke="#64748B" fontSize={11} fontFamily="ui-monospace, monospace" />
                <YAxis stroke="#64748B" fontSize={11} fontFamily="ui-monospace, monospace" allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111827',
                    borderColor: '#374151',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontFamily: 'ui-monospace, monospace',
                  }}
                />
                <Bar dataKey="count" name="Events Count" radius={[4, 4, 0, 0]}>
                  {severityChartData.map((entry, idx) => (
                    <Cell key={`sev-${idx}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Activity: Runs & Events */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Orchestration Runs */}
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-cyan-400" /> Recent Resilience Runs
            </h3>
            <button
              onClick={() => navigate('/history')}
              className="text-xs text-cyan-400 hover:text-cyan-300 font-mono transition-colors"
            >
              View All Runs &rarr;
            </button>
          </div>

          <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
            {runs.slice(0, 5).map((r) => (
              <div
                key={r.run_id}
                onClick={() => navigate(`/orchestration?run_id=${encodeURIComponent(r.run_id)}`)}
                className="p-3 rounded-lg bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition-all cursor-pointer text-xs font-mono group"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white group-hover:text-cyan-300 transition-colors">
                    {r.run_id}
                  </span>
                  <StatusBadge status={r.status} size="sm" />
                </div>
                <div className="text-slate-400 mt-1 truncate">
                  Goal: &ldquo;{r.goal}&rdquo;
                </div>
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/60 text-[11px] text-slate-500">
                  <span>Stage: {r.stage}</span>
                  <span>{r.created_at ? new Date(r.created_at).toLocaleTimeString() : '—'}</span>
                </div>
              </div>
            ))}

            {runs.length === 0 && (
              <div className="p-8 text-center text-xs text-slate-500 font-mono italic">
                No orchestration runs recorded yet. Launch a run using the button above.
              </div>
            )}
          </div>
        </div>

        {/* Recent Telemetry Stream */}
        <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" /> Real-Time Telemetry Feed
            </h3>
            <button
              onClick={() => navigate('/detection')}
              className="text-xs text-cyan-400 hover:text-cyan-300 font-mono transition-colors"
            >
              Sentinel Log &rarr;
            </button>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {recentEvents.slice(0, 6).map((evt) => (
              <div
                key={evt.id}
                className="p-2.5 rounded-lg bg-slate-900/40 border border-slate-800/80 text-xs font-mono"
              >
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-slate-300">{evt.event_type}</span>
                  <span className="text-slate-500">
                    {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : '—'}
                  </span>
                </div>
                <p className="text-slate-400 mt-1 truncate">{evt.message}</p>
              </div>
            ))}

            {recentEvents.length === 0 && (
              <div className="p-8 text-center text-xs text-slate-500 font-mono italic">
                No telemetry events logged yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
