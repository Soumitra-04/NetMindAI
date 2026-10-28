import React from 'react';
import {
  Server,
  Router as RouterIcon,
  HardDrive,
  Shield,
  Laptop,
} from 'lucide-react';
import { NetworkLink, NetworkNode } from '../../api/types';

interface TopologyCanvasProps {
  nodes: NetworkNode[];
  links: NetworkLink[];
  selectedNodeId: string | null;
  onSelectNode: (node: NetworkNode | null) => void;
}

// Preset visual coordinates for the 6 demo nodes in an intuitive NOC topology layout
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  'client-1': { x: 90, y: 200 },
  'switch-1': { x: 260, y: 200 },
  'router-1': { x: 440, y: 130 },
  'firewall-1': { x: 440, y: 290 },
  'server-1': { x: 650, y: 130 },
  'server-2': { x: 650, y: 290 },
};

export const TopologyCanvas: React.FC<TopologyCanvasProps> = ({
  nodes,
  links,
  selectedNodeId,
  onSelectNode,
}) => {
  const getNodePosition = (id: string) => {
    return NODE_POSITIONS[id] || { x: 350, y: 200 };
  };

  const getNodeIcon = (type: string) => {
    switch (type) {
      case 'server':
        return Server;
      case 'router':
        return RouterIcon;
      case 'switch':
        return HardDrive;
      case 'firewall':
        return Shield;
      case 'host':
      default:
        return Laptop;
    }
  };

  return (
    <div className="relative w-full h-[450px] bg-[#080D1A] rounded-xl border border-slate-800 overflow-hidden select-none">
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage:
            'radial-gradient(#38BDF8 1px, transparent 1px), radial-gradient(#1E293B 1px, #080D1A 1px)',
          backgroundSize: '30px 30px',
          backgroundPosition: '0 0, 15px 15px',
        }}
      />

      <svg className="w-full h-full">
        {/* Render Links */}
        {links.map((link, idx) => {
          const srcPos = getNodePosition(link.source);
          const tgtPos = getNodePosition(link.target);
          const isRedundant =
            (link.source === 'switch-1' && link.target === 'server-1') ||
            (link.source === 'server-1' && link.target === 'switch-1');

          const midX = (srcPos.x + tgtPos.x) / 2;
          const midY = (srcPos.y + tgtPos.y) / 2;

          return (
            <g key={`${link.source}-${link.target}-${idx}`}>
              <line
                x1={srcPos.x}
                y1={srcPos.y}
                x2={tgtPos.x}
                y2={tgtPos.y}
                stroke={link.active ? (isRedundant ? '#8B5CF6' : '#06B6D4') : '#EF4444'}
                strokeWidth={link.active ? 2.5 : 2}
                strokeDasharray={!link.active ? '5,5' : isRedundant ? '4,4' : undefined}
                className="transition-all duration-300"
              />

              {/* Latency badge on link center */}
              <rect
                x={midX - 22}
                y={midY - 9}
                width="44"
                height="18"
                rx="4"
                fill="#0F172A"
                stroke={link.active ? (isRedundant ? '#8B5CF6' : '#1E293B') : '#EF4444'}
                strokeWidth="1"
              />
              <text
                x={midX}
                y={midY + 3}
                fill={link.active ? '#94A3B8' : '#FCA5A5'}
                fontSize="9"
                fontFamily="ui-monospace, monospace"
                textAnchor="middle"
              >
                {link.active ? `${link.latency_ms}ms` : 'DOWN'}
              </text>
            </g>
          );
        })}

        {/* Render Nodes */}
        {nodes.map((node) => {
          const pos = getNodePosition(node.id);
          const isSelected = selectedNodeId === node.id;
          const Icon = getNodeIcon(node.type);

          return (
            <g
              key={node.id}
              transform={`translate(${pos.x}, ${pos.y})`}
              className="cursor-pointer group"
              onClick={() => onSelectNode(isSelected ? null : node)}
            >
              {/* Pulse glow if selected */}
              {isSelected && (
                <circle
                  r="32"
                  fill="none"
                  stroke="#38BDF8"
                  strokeWidth="2"
                  className="animate-ping opacity-30"
                />
              )}

              {/* Node Outer Circle */}
              <circle
                r="24"
                fill="#111827"
                stroke={
                  !node.active
                    ? '#EF4444'
                    : isSelected
                    ? '#38BDF8'
                    : '#1E293B'
                }
                strokeWidth={isSelected ? 2.5 : 1.5}
                className="transition-all duration-200 group-hover:stroke-cyan-400 shadow-lg"
              />

              {/* Node Icon */}
              <foreignObject x="-10" y="-10" width="20" height="20">
                <Icon
                  className={`w-5 h-5 ${
                    !node.active
                      ? 'text-rose-400'
                      : isSelected
                      ? 'text-cyan-300'
                      : 'text-slate-300'
                  }`}
                />
              </foreignObject>

              {/* Active / Inactive Status Dot */}
              <circle
                cx="15"
                cy="-15"
                r="4.5"
                fill={node.active ? '#10B981' : '#EF4444'}
                stroke="#0B0F19"
                strokeWidth="1.5"
              />

              {/* Node Label Below */}
              <text
                y="38"
                fill={isSelected ? '#38BDF8' : '#E2E8F0'}
                fontSize="11"
                fontWeight="600"
                fontFamily="ui-sans-serif, system-ui, sans-serif"
                textAnchor="middle"
                className="select-none"
              >
                {node.name}
              </text>

              {/* IP / Type Subtitle */}
              <text
                y="50"
                fill="#64748B"
                fontSize="9"
                fontFamily="ui-monospace, monospace"
                textAnchor="middle"
                className="select-none"
              >
                {node.ip_address || node.type}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend overlay */}
      <div className="absolute bottom-3 left-3 bg-[#0B0F19]/90 border border-slate-800 p-2.5 rounded-lg text-[10px] font-mono text-slate-400 space-y-1 backdrop-blur pointer-events-none">
        <div className="flex items-center gap-2">
          <span className="w-3 h-0.5 bg-cyan-400 inline-block" /> Primary Active Link
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-0.5 bg-violet-400 inline-block border-b border-dashed border-violet-400" /> Redundant Failover Link
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-0.5 bg-rose-500 inline-block" /> Disabled / Disrupted Link
        </div>
      </div>
    </div>
  );
};
