import React, { useEffect, useState, useCallback } from 'react';
import {
  HeartPulse,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { healthApi } from '../api/health';
import { simulationApi } from '../api/simulation';
import { eventsApi } from '../api/events';
import { blueApi } from '../api/blue';
import { orchestrationApi } from '../api/orchestration';
import { LoadingState } from '../components/common/LoadingState';

interface ServiceCheck {
  name: string;
  endpoint: string;
  status: 'healthy' | 'degraded' | 'unavailable' | 'unknown';
  latencyMs?: number;
  message: string;
  details?: Record<string, unknown>;
}

export const SystemHealthPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [services, setServices] = useState<ServiceCheck[]>([]);

  const runDiagnostics = useCallback(async () => {
    setLoading(true);
    const checks: ServiceCheck[] = [];

    // 1. FastAPI Main Health
    const t0 = performance.now();
    try {
      const res = await healthApi.check();
      checks.push({
        name: 'FastAPI Application Server',
        endpoint: 'GET /health',
        status: res.status === 'healthy' ? 'healthy' : 'degraded',
        latencyMs: Math.round(performance.now() - t0),
        message: 'FastAPI core router is responsive and accepting HTTP requests.',
      });
    } catch (err: any) {
      checks.push({
        name: 'FastAPI Application Server',
        endpoint: 'GET /health',
        status: 'unavailable',
        latencyMs: Math.round(performance.now() - t0),
        message: err.message || 'Cannot establish connection to FastAPI backend.',
      });
    }

    // 2. Network Simulation Engine
    const t1 = performance.now();
    try {
      const sim = await simulationApi.getState();
      checks.push({
        name: 'Network Simulation Controller',
        endpoint: 'GET /simulation/state',
        status: 'healthy',
        latencyMs: Math.round(performance.now() - t1),
        message: `Topology initialized with ${sim.topology.nodes.length} nodes and ${sim.topology.links.length} links.`,
        details: {
          step: sim.step_number,
          flows: sim.flows.length,
          activeNodes: sim.topology.nodes.filter((n) => n.active).length,
        },
      });
    } catch (err: any) {
      checks.push({
        name: 'Network Simulation Controller',
        endpoint: 'GET /simulation/state',
        status: 'unavailable',
        latencyMs: Math.round(performance.now() - t1),
        message: 'Simulation engine snapshot unreachable.',
      });
    }

    // 3. Telemetry & Event Persistence
    const t2 = performance.now();
    try {
      const evts = await eventsApi.getEvents({ limit: 5 });
      checks.push({
        name: 'Telemetry & Event Persistence Service',
        endpoint: 'GET /events/',
        status: 'healthy',
        latencyMs: Math.round(performance.now() - t2),
        message: 'Event ledger and DuckDB/jsonl stream actively persisting.',
        details: { recentEventsCount: evts.length },
      });
    } catch (err: any) {
      checks.push({
        name: 'Telemetry & Event Persistence Service',
        endpoint: 'GET /events/',
        status: 'unavailable',
        latencyMs: Math.round(performance.now() - t2),
        message: 'Unable to query event service.',
      });
    }

    // 4. LangGraph Orchestrator
    const t3 = performance.now();
    try {
      const runs = await orchestrationApi.listRuns();
      checks.push({
        name: 'LangGraph Orchestration State Machine',
        endpoint: 'GET /orchestration/runs',
        status: 'healthy',
        latencyMs: Math.round(performance.now() - t3),
        message: 'Checkpoint state manager operational with in-memory graph runner.',
        details: { trackedRuns: runs.length },
      });
    } catch (err: any) {
      checks.push({
        name: 'LangGraph Orchestration State Machine',
        endpoint: 'GET /orchestration/runs',
        status: 'unavailable',
        latencyMs: Math.round(performance.now() - t3),
        message: 'Orchestrator graph manager returned error.',
      });
    }

    // 5. Blue Sentinel & Blue Response
    const t4 = performance.now();
    try {
      const recs = await blueApi.listRecommendations();
      checks.push({
        name: 'Blue Response Mitigation Subsystem',
        endpoint: 'GET /blue/response/recommendations',
        status: 'healthy',
        latencyMs: Math.round(performance.now() - t4),
        message: 'Response recommendation and approval guards operational.',
        details: { recommendationsCount: recs.length },
      });
    } catch (err: any) {
      checks.push({
        name: 'Blue Response Mitigation Subsystem',
        endpoint: 'GET /blue/response/recommendations',
        status: 'unavailable',
        latencyMs: Math.round(performance.now() - t4),
        message: 'Blue Response API returned error.',
      });
    }

    // 6. Baseline Random Forest ML Model (Honest Status)
    checks.push({
      name: 'Random Forest Intrusion Model (CICIDS-2017)',
      endpoint: 'models/baseline_random_forest.joblib',
      status: 'unavailable',
      message:
        'Trained model expects 67 CICIDS flow features. Live abstract graph simulator intentionally does NOT fabricate synthetic packet metrics; model is evaluated via standalone test suite.',
      details: {
        artifactPath: 'models/baseline_random_forest.joblib',
        expectedFeatures: 67,
        threshold: 0.3065,
        targetMapping: { BENIGN: 0, ATTACK: 1 },
      },
    });

    // 7. Ollama / Qwen LLM Service
    checks.push({
      name: 'Ollama LLM Client (Qwen3:4B)',
      endpoint: 'http://localhost:11434 (Optional)',
      status: 'unknown',
      message:
        'When local Ollama is offline, orchestrator safely falls back to deterministic allowlisted scenarios without blocking resilience workflows.',
    });

    setServices(checks);
    setLastCheck(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    runDiagnostics();
  }, [runDiagnostics]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
      case 'degraded':
        return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case 'unavailable':
        return <XCircle className="w-4 h-4 text-rose-400" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-slate-500" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-[#0D1322]">
        <div>
          <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wide flex items-center gap-2">
            <HeartPulse className="w-4 h-4 text-cyan-400" />
            Backend Subsystem Diagnostics &amp; Model Availability
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real health checks across API endpoints, graph orchestration, simulator, and ML model dependencies.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-400">
            Last Checked:{' '}
            <span className="text-slate-200">
              {lastCheck ? lastCheck.toLocaleTimeString() : '—'}
            </span>
          </span>

          <button
            onClick={runDiagnostics}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            Run Diagnostics
          </button>
        </div>
      </div>

      {loading && services.length === 0 ? (
        <LoadingState message="Probing Backend Endpoints &amp; Subsystems..." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {services.map((svc, idx) => (
            <div
              key={idx}
              className="p-5 rounded-xl border border-slate-800 bg-[#0D1322] shadow-xl space-y-3 font-mono text-xs flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <h3 className="font-bold text-white text-sm">{svc.name}</h3>
                    <span className="text-[11px] text-slate-500">{svc.endpoint}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {getStatusIcon(svc.status)}
                    <span
                      className={`font-semibold capitalize text-xs ${
                        svc.status === 'healthy'
                          ? 'text-emerald-400'
                          : svc.status === 'unavailable'
                          ? 'text-rose-400'
                          : svc.status === 'degraded'
                          ? 'text-amber-400'
                          : 'text-slate-500'
                      }`}
                    >
                      {svc.status}
                    </span>
                  </div>
                </div>

                <p className="text-slate-300 text-xs leading-relaxed mt-2">
                  {svc.message}
                </p>
              </div>

              <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
                <span>
                  {svc.latencyMs !== undefined ? `RTT: ${svc.latencyMs} ms` : 'Static Assessment'}
                </span>
                {svc.details && (
                  <span className="text-slate-400">
                    {Object.entries(svc.details)
                      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
                      .join(' | ')}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
