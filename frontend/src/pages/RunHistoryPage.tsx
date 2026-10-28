import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  History,
  Search,
  ArrowUpDown,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { orchestrationApi } from '../api/orchestration';
import { OrchestrationRunResponse } from '../api/types';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const RunHistoryPage: React.FC = () => {
  const navigate = useNavigate();

  const [runs, setRuns] = useState<OrchestrationRunResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  const fetchRuns = useCallback(async (silent = false) => {
    if (!silent) setIsRefreshing(true);
    try {
      const data = await orchestrationApi.listRuns(statusFilter || undefined);
      setRuns(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch runs');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const filteredRuns = runs
    .filter((r) => {
      if (!searchTerm) return true;
      const term = searchTerm.toLowerCase();
      return (
        r.run_id.toLowerCase().includes(term) ||
        r.goal.toLowerCase().includes(term) ||
        (r.scenario_id && r.scenario_id.toLowerCase().includes(term))
      );
    })
    .sort((a, b) => {
      const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return sortOrder === 'desc' ? timeB - timeA : timeA - timeB;
    });

  if (loading && runs.length === 0) {
    return <LoadingState message="Loading Orchestration Run Audit Logs..." />;
  }

  if (error && runs.length === 0) {
    return <ErrorState message={error} onRetry={() => fetchRuns()} />;
  }

  return (
    <div className="space-y-6">
      {/* Top filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div>
          <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <History className="w-4 h-4 text-cyan-400" />
            Orchestration Run Audit Ledger
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Complete historical audit trail of executed resilience workflows.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Search box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search run ID or goal..."
              className="pl-8 pr-3 py-1.5 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-200 placeholder-slate-500 font-mono w-52 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Status filter dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-md bg-slate-900 border border-slate-700 text-slate-300 font-mono focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Statuses</option>
            <option value="running">running</option>
            <option value="pending_approval">pending_approval</option>
            <option value="completed">completed</option>
            <option value="completed_healthy">completed_healthy</option>
            <option value="completed_no_action">completed_no_action</option>
            <option value="rejected">rejected</option>
            <option value="failed">failed</option>
          </select>

          {/* Sort toggle */}
          <button
            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono transition-colors"
          >
            <ArrowUpDown className="w-3 h-3 text-cyan-400" />
            {sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}
          </button>

          <button
            onClick={() => fetchRuns()}
            disabled={isRefreshing}
            className="p-1.5 rounded-md border border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table view */}
      <div className="rounded-xl border border-slate-800 bg-[#0D1322] overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#0A0E17] border-b border-slate-800 text-slate-400 uppercase tracking-wider text-[11px]">
              <tr>
                <th className="py-3 px-4">Run Identifier</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Stage</th>
                <th className="py-3 px-4">Goal Description</th>
                <th className="py-3 px-4">Scenario</th>
                <th className="py-3 px-4">Approver</th>
                <th className="py-3 px-4">Timestamp</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {filteredRuns.map((r) => (
                <tr
                  key={r.run_id}
                  onClick={() => navigate(`/orchestration?run_id=${encodeURIComponent(r.run_id)}`)}
                  className="hover:bg-slate-900/40 transition-colors cursor-pointer group"
                >
                  <td className="py-3.5 px-4 font-bold text-white group-hover:text-cyan-300">
                    {r.run_id}
                  </td>
                  <td className="py-3.5 px-4">
                    <StatusBadge status={r.status} size="sm" />
                  </td>
                  <td className="py-3.5 px-4 text-slate-300">
                    {r.stage}
                  </td>
                  <td className="py-3.5 px-4 text-slate-300 max-w-xs truncate">
                    {r.goal}
                  </td>
                  <td className="py-3.5 px-4 text-slate-400">
                    {r.scenario_id || (r.skip_disruption ? 'none (baseline)' : 'auto')}
                  </td>
                  <td className="py-3.5 px-4 text-slate-400">
                    {r.approver || '—'}
                  </td>
                  <td className="py-3.5 px-4 text-slate-500 whitespace-nowrap">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <span className="text-cyan-400 group-hover:text-cyan-300 inline-flex items-center gap-1 font-semibold">
                      Inspect <ExternalLink className="w-3 h-3" />
                    </span>
                  </td>
                </tr>
              ))}

              {filteredRuns.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-500 italic">
                    No runs match the specified search or filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
