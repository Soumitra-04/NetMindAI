import React from 'react';
import { X, Network, Activity } from 'lucide-react';
import { NetworkLink, NetworkNode, TrafficFlow } from '../../api/types';
import { StatusBadge } from '../common/StatusBadge';

interface NodeDetailDrawerProps {
  node: NetworkNode | null;
  links: NetworkLink[];
  flows: TrafficFlow[];
  onClose: () => void;
}

export const NodeDetailDrawer: React.FC<NodeDetailDrawerProps> = ({
  node,
  links,
  flows,
  onClose,
}) => {
  if (!node) return null;

  const connectedLinks = links.filter(
    (l) => l.source === node.id || l.target === node.id
  );

  const relatedFlows = flows.filter(
    (f) => f.source === node.id || f.destination === node.id
  );

  return (
    <div className="rounded-xl border border-slate-800 bg-[#0D1322] p-5 shadow-xl space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-white font-mono">{node.name}</h3>
            <StatusBadge status={node.active ? 'active' : 'inactive'} size="sm" />
          </div>
          <span className="text-xs font-mono text-slate-400">ID: {node.id}</span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 transition-colors p-1"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs font-mono">
        <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
          <span className="text-[10px] text-slate-500 uppercase block">Device Type</span>
          <span className="text-slate-200 capitalize font-medium">{node.type}</span>
        </div>
        <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
          <span className="text-[10px] text-slate-500 uppercase block">IP Address</span>
          <span className="text-cyan-300 font-medium">{node.ip_address || 'None (Layer 2)'}</span>
        </div>
      </div>

      {/* Connected Links */}
      <div>
        <h4 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Network className="w-3.5 h-3.5 text-cyan-400" />
          Connected Links ({connectedLinks.length})
        </h4>
        <div className="space-y-1.5 max-h-36 overflow-y-auto">
          {connectedLinks.map((link, idx) => {
            const peer = link.source === node.id ? link.target : link.source;
            return (
              <div
                key={idx}
                className="flex items-center justify-between p-2 rounded bg-slate-900/40 border border-slate-800 text-xs font-mono"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      link.active ? 'bg-emerald-400' : 'bg-rose-500'
                    }`}
                  />
                  <span className="text-slate-300">{peer}</span>
                </div>
                <div className="flex items-center gap-3 text-slate-400 text-[11px]">
                  <span>{link.latency_ms}ms</span>
                  <span>{link.bandwidth_mbps} Mbps</span>
                  <span className={link.active ? 'text-emerald-400' : 'text-rose-400'}>
                    {link.active ? 'UP' : 'DOWN'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Related Flows */}
      <div>
        <h4 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-violet-400" />
          Associated Traffic Flows ({relatedFlows.length})
        </h4>
        <div className="space-y-1.5 max-h-36 overflow-y-auto">
          {relatedFlows.map((flow) => (
            <div
              key={flow.id}
              className="p-2 rounded bg-slate-900/40 border border-slate-800 text-xs font-mono space-y-1"
            >
              <div className="flex items-center justify-between">
                <span className="text-cyan-300 font-semibold">{flow.id}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded ${
                    flow.reachable
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                  }`}
                >
                  {flow.reachable ? 'REACHABLE' : 'UNREACHABLE'}
                </span>
              </div>
              <div className="text-[11px] text-slate-400">
                {flow.source} &rarr; {flow.destination} ({flow.protocol}, {flow.packets_per_second} pps)
              </div>
            </div>
          ))}
          {relatedFlows.length === 0 && (
            <div className="text-xs text-slate-500 italic p-2 font-mono">
              No registered flows terminate directly on this node.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
