import React, { useEffect, useState, useCallback } from 'react';
import {
  Network,
  RotateCcw,
  StepForward,
  Info,
} from 'lucide-react';
import { simulationApi } from '../api/simulation';
import { NetworkNode, SimulationSnapshot } from '../api/types';
import { TopologyCanvas } from '../components/topology/TopologyCanvas';
import { NodeDetailDrawer } from '../components/topology/NodeDetailDrawer';
import { MetricCard } from '../components/common/MetricCard';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { ConfirmationDialog } from '../components/common/ConfirmationDialog';

export const TopologyPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null);

  // Stepping / Resetting states
  const [isStepping, setIsStepping] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const fetchTopologyState = useCallback(async () => {
    try {
      const data = await simulationApi.getState();
      setSnapshot(data);
      if (selectedNode) {
        const updated = data.topology.nodes.find((n) => n.id === selectedNode.id);
        if (updated) setSelectedNode(updated);
      }
      setError(null);
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to fetch topology snapshot');
    } finally {
      setLoading(false);
    }
  }, [selectedNode]);

  useEffect(() => {
    fetchTopologyState();
  }, [fetchTopologyState]);

  const handleStep = async () => {
    setIsStepping(true);
    try {
      const data = await simulationApi.step();
      setSnapshot(data);
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to advance simulation step');
    } finally {
      setIsStepping(false);
    }
  };

  const handleReset = async () => {
    setIsResetting(true);
    try {
      const data = await simulationApi.reset();
      setSnapshot(data);
      setSelectedNode(null);
      setShowResetConfirm(false);
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to reset simulation');
    } finally {
      setIsResetting(false);
    }
  };

  if (loading && !snapshot) {
    return <LoadingState message="Retrieving Network Topology &amp; Physical Link States..." />;
  }

  if (error && !snapshot) {
    return (
      <ErrorState
        title="Topology Service Unreachable"
        message={error}
        onRetry={fetchTopologyState}
      />
    );
  }

  const nodes = snapshot?.topology.nodes || [];
  const links = snapshot?.topology.links || [];
  const flows = snapshot?.flows || [];
  const metrics = snapshot?.metrics;

  const totalNodes = nodes.length;
  const activeNodes = nodes.filter((n) => n.active).length;
  const totalLinks = links.length;
  const activeLinks = links.filter((l) => l.active).length;

  return (
    <div className="space-y-6">
      {/* Top action bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div>
          <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <Network className="w-4 h-4 text-cyan-400" />
            Network Topology Graph &amp; State Inspector
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Interactive representation of simulator nodes, bidirectional links, and pathfinding.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs font-mono text-slate-400 bg-slate-900 px-3 py-1.5 rounded-md border border-slate-800">
            Step: <span className="text-cyan-300 font-bold">#{snapshot?.step_number ?? 0}</span>
          </div>

          <button
            onClick={handleStep}
            disabled={isStepping}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono transition-colors disabled:opacity-50"
          >
            <StepForward className="w-3.5 h-3.5 text-cyan-400" />
            Advance Step
          </button>

          <button
            onClick={() => setShowResetConfirm(true)}
            disabled={isResetting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-500/40 text-xs font-mono transition-colors disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5 text-rose-400" />
            Reset Topology
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCard
          title="Active Nodes"
          value={`${activeNodes} / ${totalNodes}`}
          variant={activeNodes === totalNodes ? 'emerald' : 'amber'}
        />
        <MetricCard
          title="Active Links"
          value={`${activeLinks} / ${totalLinks}`}
          variant={activeLinks === totalLinks ? 'emerald' : 'rose'}
        />
        <MetricCard
          title="Average Path Latency"
          value={
            metrics?.traffic.average_path_latency_ms !== null &&
            metrics?.traffic.average_path_latency_ms !== undefined
              ? `${metrics.traffic.average_path_latency_ms} ms`
              : 'N/A'
          }
          variant="cyan"
        />
        <MetricCard
          title="Total Offered Load"
          value={
            metrics?.traffic.total_offered_mbps !== undefined
              ? `${metrics.traffic.total_offered_mbps} Mbps`
              : 'N/A'
          }
          variant="violet"
        />
      </div>

      {/* Main Graph & Inspector Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <TopologyCanvas
            nodes={nodes}
            links={links}
            selectedNodeId={selectedNode?.id || null}
            onSelectNode={setSelectedNode}
          />
        </div>

        <div>
          {selectedNode ? (
            <NodeDetailDrawer
              node={selectedNode}
              links={links}
              flows={flows}
              onClose={() => setSelectedNode(null)}
            />
          ) : (
            <div className="h-full rounded-xl border border-slate-800 bg-[#0D1322] p-8 flex flex-col items-center justify-center text-center">
              <Info className="w-8 h-8 text-slate-500 mb-3" />
              <h3 className="text-sm font-semibold text-slate-300">No Device Selected</h3>
              <p className="mt-1 text-xs text-slate-500 max-w-xs font-mono">
                Click on any host, router, switch, firewall, or server in the topology canvas to inspect live properties, connected links, and flows.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Explicit Simulation Limitations info banner */}
      {metrics?.limitations && metrics.limitations.length > 0 && (
        <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/40 text-xs font-mono text-slate-400 space-y-1">
          <span className="text-slate-300 font-semibold uppercase block text-[10px]">
            Simulator Architecture &amp; Telemetry Notice
          </span>
          {metrics.limitations.map((lim, idx) => (
            <div key={idx} className="flex items-center gap-2 text-slate-400">
              <span className="text-cyan-400">•</span>
              <span>{lim}</span>
            </div>
          ))}
        </div>
      )}

      {/* Confirmation Dialog for Reset */}
      <ConfirmationDialog
        isOpen={showResetConfirm}
        title="Reset Network Simulation"
        description="Are you sure you want to reset the network simulation? This will restore all demo nodes, re-enable disabled links, and restore baseline traffic flows."
        confirmLabel="Yes, Reset Simulation"
        confirmVariant="danger"
        isLoading={isResetting}
        onConfirm={handleReset}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  );
};
