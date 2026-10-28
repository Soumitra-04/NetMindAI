import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CreateRunModal } from '../orchestration/CreateRunModal';
import { OrchestrationRunResponse } from '../../api/types';

interface AppLayoutProps {
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  onRefresh,
  isRefreshing = false,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const getPageTitle = (pathname: string): string => {
    if (pathname === '/') return 'Network Operations Center — Overview';
    if (pathname.startsWith('/topology')) return 'Network Topology Map & Inspector';
    if (pathname.startsWith('/simulation')) return 'Red Agent — Fault Simulation Engine';
    if (pathname.startsWith('/detection')) return 'Blue Sentinel — Autonomous Detection & Response';
    if (pathname.startsWith('/orchestration')) return 'LangGraph Resilience Orchestrator';
    if (pathname.startsWith('/approvals')) return 'Human-in-the-Loop Approval Gate';
    if (pathname.startsWith('/history')) return 'Orchestration Run Audit History';
    if (pathname.startsWith('/health')) return 'System Diagnostics & Model Availability';
    return 'NetMind Resilience Console';
  };

  const handleRunCreated = (run: OrchestrationRunResponse) => {
    navigate(`/orchestration?run_id=${encodeURIComponent(run.run_id)}`);
  };

  return (
    <div className="flex h-screen bg-[#0B0F19] text-slate-100 overflow-hidden font-sans">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
      />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar
          title={getPageTitle(location.pathname)}
          onRefresh={onRefresh}
          isRefreshing={isRefreshing}
          onOpenCreateRun={() => setIsCreateModalOpen(true)}
        />

        <main className="flex-1 overflow-y-auto p-6 bg-[#0B0F19]">
          <Outlet />
        </main>
      </div>

      <CreateRunModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onRunCreated={handleRunCreated}
      />
    </div>
  );
};

