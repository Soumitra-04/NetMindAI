import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { BackendStatusProvider } from './context/BackendStatusContext';
import { AppLayout } from './components/layout/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { TopologyPage } from './pages/TopologyPage';
import { RedAgentPage } from './pages/RedAgentPage';
import { BlueAgentPage } from './pages/BlueAgentPage';
import { OrchestrationPage } from './pages/OrchestrationPage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { RunHistoryPage } from './pages/RunHistoryPage';
import { SystemHealthPage } from './pages/SystemHealthPage';

export const App: React.FC = () => {
  return (
    <BackendStatusProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="topology" element={<TopologyPage />} />
            <Route path="simulation" element={<RedAgentPage />} />
            <Route path="detection" element={<BlueAgentPage />} />
            <Route path="orchestration" element={<OrchestrationPage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="history" element={<RunHistoryPage />} />
            <Route path="health" element={<SystemHealthPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </BackendStatusProvider>
  );
};

export default App;

