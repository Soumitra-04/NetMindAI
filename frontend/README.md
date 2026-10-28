# NetMind Frontend — Network Resilience & AI Orchestration Dashboard

The frontend is a dedicated Network Operations Center (NOC) and autonomous recovery dashboard built with modern React, TypeScript, and Tailwind CSS.

---

## Features

- **Network Operations Center (Overview)**: Live telemetry metrics, node/link counts, active runs, pending approvals, and Recharts visualizations for flow latencies and event distribution.
- **Interactive Topology Map**: Full graph representation of simulated network devices (Client, Switch, Router, Firewall, Servers) with real-time link latency badges, active/down indicators, and device properties drawer.
- **Red Agent Simulation Launchpad**: Disruption injector supporting `link_disruption` and `server_disruption` scenarios with safety confirmation dialogs.
- **Blue Sentinel & Response Console**: Autonomous inspection scanner with findings log, ML model status transparency, recommendation cards, and one-click execution.
- **LangGraph Orchestration Workspace**: Real-time visual graph representation of the 11 checkpointed stages, highlighting active, completed, skipped, and approval-paused states.
- **Human-in-the-Loop Approval Center**: Dedicated operator inbox with clear action rationale, expected effect, operator handle logging, and explicit Approve/Reject controls.
- **Run Audit Ledger**: Historical table with run ID search, status filters, timestamp sorting, and direct links to run detail graphs.
- **System Diagnostics**: Live connection monitor with ping RTT, backend service health checks, and honest dependency indicators.

---

## Setup & Running

```powershell
# 1. Install dependencies
npm install

# 2. Start local dev server (default port 5173 with API proxy)
npm run dev

# 3. Build for production (TypeScript checking + Vite bundle)
npm run build
```

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL for the FastAPI backend |

