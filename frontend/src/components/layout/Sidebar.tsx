import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  Network,
  Flame,
  Shield,
  GitBranch,
  CheckCircle,
  History,
  HeartPulse,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  pendingApprovalsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggle,
  pendingApprovalsCount = 0,
}) => {
  const navItems = [
    { name: 'Overview', path: '/', icon: Activity },
    { name: 'Network Topology', path: '/topology', icon: Network },
    { name: 'Simulations / Red Agent', path: '/simulation', icon: Flame },
    { name: 'Detection / Blue Sentinel', path: '/detection', icon: Shield },
    { name: 'Orchestration', path: '/orchestration', icon: GitBranch },
    {
      name: 'Approvals',
      path: '/approvals',
      icon: CheckCircle,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
    },
    { name: 'Run History', path: '/history', icon: History },
    { name: 'System Health', path: '/health', icon: HeartPulse },
  ];

  return (
    <aside
      className={`relative flex flex-col border-r border-slate-800 bg-[#0D1322] transition-all duration-300 z-30 select-none ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-slate-800/80">
        {!collapsed ? (
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono font-bold text-sm shadow-[0_0_10px_rgba(6,182,212,0.2)]">
              NM
            </div>
            <div className="flex flex-col">
              <span className="font-bold tracking-tight text-white text-sm font-sans flex items-center gap-1.5">
                NetMind <span className="text-[10px] text-cyan-400 font-mono bg-cyan-950 px-1 py-0.2 rounded border border-cyan-800">NOC</span>
              </span>
              <span className="text-[10px] font-mono text-slate-400 tracking-wider">
                Autonomous Recovery
              </span>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex items-center justify-center w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono font-bold text-sm">
            NM
          </div>
        )}
      </div>

      {/* Nav List */}
      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              title={collapsed ? item.name : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-medium transition-all group ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.15)] font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                } ${collapsed ? 'justify-center px-0' : ''}`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && (
                <span className="flex-1 truncate tracking-wide">
                  {item.name}
                </span>
              )}
              {!collapsed && item.badge !== undefined && (
                <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
                  {item.badge}
                </span>
              )}
              {collapsed && item.badge !== undefined && (
                <span className="absolute top-1 right-2 w-2 h-2 rounded-full bg-amber-400" />
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Collapse Toggle */}
      <div className="p-3 border-t border-slate-800/80">
        <button
          onClick={onToggle}
          className="flex items-center justify-center w-full py-2 rounded-md text-xs font-mono text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <div className="flex items-center gap-2">
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse Sidebar</span>
            </div>
          )}
        </button>
      </div>
    </aside>
  );
};

