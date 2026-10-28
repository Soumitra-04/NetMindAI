# NetMindAI 🌐
### AI-Driven Network Resilience & Cybersecurity Simulation

**Simulate. Detect. Respond. Recover.**

NetMindAI is an AI-powered network resilience platform that simulates controlled network disruptions and combines local Large Language Models (LLMs), network simulation, telemetry, and Machine Learning (ML) to support intelligent network monitoring and resilience analysis.

The project aims to provide a reproducible environment for studying network behavior under disruptions and developing AI-assisted detection and recovery workflows without affecting real-world infrastructure.

---

## ✨ Key Features

- **AI-Assisted Scenario Planning:** Uses a locally hosted LLM to select and explain permitted network disruption scenarios.
- **Controlled Network Simulation:** Models network nodes, links, traffic flows, connectivity, and routing behavior.
- **Resilience Testing:** Simulates link and server disruptions to observe their impact on network connectivity.
- **Network Telemetry:** Records simulation events and exposes them through backend APIs.
- **Machine Learning Inference:** Provides a Random Forest classifier for compatible network-flow feature inputs.
- **Interactive Monitoring Dashboard:** Visualizes network health, traffic latency, event distributions, simulation runs, and system status.
- **Backend API:** Uses FastAPI to expose simulation, topology, event, and other implemented functionality.
- **Local-First AI:** Integrates Ollama to run an LLM locally rather than requiring a paid cloud LLM API.

## 🏗️ Architecture

```text
                    ┌─────────────────────────┐
                    │   NetMindAI Dashboard   │
                    │      React + Vite       │
                    └────────────┬────────────┘
                                 │ HTTP
                    ┌────────────▼────────────┐
                    │       FastAPI API       │
                    │  Simulation / Topology  │
                    │      Events / Health    │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
     │    Red Agent    │ │ Network Engine │ │ Event Service  │
     │                 │ │                │ │                │
     │ Ollama + Qwen   │ │ Topology       │ │ Telemetry      │
     │ Scenario Plan   │ │ Traffic         │ │ Event Records  │
     │ Validation      │ │ Routing         │ │ Event API      │
     └────────┬────────┘ └────────────────┘ └────────────────┘
              │
     ┌────────▼────────┐
     │ Controlled      │
     │ Simulated       │
     │ Disruption      │
     └─────────────────┘


     ┌─────────────────────────────┐
     │ Random Forest Inference     │
     │ 67-feature flow classifier  │
     │ Standalone ML service       │
     └─────────────────────────────┘
```

**Important:** The Random Forest inference service is currently separate from live simulator detection. The trained classifier expects 67 CICIDS-style network-flow features, while the simulator currently models higher-level network properties. A validated feature-extraction and integration pipeline is still required to connect them.

## 🧠 Technology Stack

| Category | Technologies |
|---|---|
| Language | Python |
| Backend | FastAPI, Uvicorn |
| Frontend | React, TypeScript, Vite |
| Local LLM runtime | Ollama |
| LLM | Qwen3:4B |
| Machine Learning | scikit-learn, Random Forest |
| Data processing | NumPy, pandas |
| Validation | Pydantic |
| Testing | pytest |
| Network simulation | Custom in-memory simulation engine |
| API communication | HTTP, JSON |

## ⚙️ How It Works

### 1. Scenario Planning

The Red Agent sends the experiment goal and a summary of the simulated network to the local LLM. The LLM returns a structured scenario selection and rationale.

The application validates the response against an allowlist before execution.

### 2. Network Simulation

The simulation engine applies a permitted disruption to the in-memory network. It updates the relevant node or link state and allows the simulator to evaluate connectivity and routing.

### 3. Telemetry and Event Recording

Simulation events are recorded through the telemetry system and can be retrieved through the backend event API. The dashboard uses backend responses to display network status, traffic information, and recent events.

### 4. Machine Learning Inference

The standalone Random Forest service validates compatible feature inputs and returns a prediction, attack probability, and threshold-based classification. It does not automatically classify the simulator's traffic until a valid feature adapter is implemented.

### 5. Dashboard Monitoring

The web dashboard provides an interface for inspecting topology, traffic latency, events, simulation runs, approvals, and system status according to the functionality implemented by the backend.

## 🧪 Supported Simulation Scenarios

### Link Disruption

Disables a selected simulated network link.

This scenario can be used to observe whether alternate paths preserve connectivity and how the available route changes.

### Server Disruption

Deactivates a simulated server node.

This scenario can be used to observe destination unavailability and the impact on traffic flows targeting the affected node.

All disruption scenarios operate within the simulated network. They do not attack physical infrastructure or external systems.

## 🤖 Machine Learning Model

The existing model artifact is:

`models/baseline_random_forest.joblib`

| Property | Value |
|---|---|
| Model | Random Forest Classifier |
| Input features | 67 |
| Classification labels | `BENIGN`, `ATTACK` |
| Decision threshold | Approximately `0.3065` |
| Inference service | `backend/services/inference_service.py` |

The inference service validates feature names, ordering, numeric values, and non-finite inputs before prediction.

The model must receive the feature representation it was trained on. Missing features are not fabricated to force predictions.

## 📊 Dashboard

The NetMindAI dashboard includes views for:

- **Overview:** Network health, traffic latency, event distributions, recent runs, and telemetry.
- **Network Topology:** Visualization and inspection of simulated network nodes and links.
- **Simulations / Red Agent:** Access to implemented simulation functionality.
- **Detection / Blue Sentinel:** Interface for detection functionality as it becomes available.
- **Orchestration:** View of implemented orchestration functionality.
- **Approvals:** Approval-related interface where supported by the backend.
- **Run History:** Experiment history where supported.
- **System Health:** Backend and dependency status.

The availability of each feature depends on its actual backend implementation. Planned features may appear as unavailable until their workflows are complete.

## 🚀 Getting Started

### Prerequisites

Install or prepare the following:

- Python 3.13.x, consistent with the project's `.python-version` and dependency configuration.
- Node.js and npm.
- Git.
- Ollama, if you want to use the local LLM functionality.
- The trained model artifact at `models/baseline_random_forest.joblib`, if you want to use ML inference.

### 1. Clone the Repository

```bash
git clone https://github.com/Soumitra-04/NetMindAI.git
cd NetMindAI
```

### 2. Set Up the Python Environment

If the repository uses a checked-in `uv.lock` file and `uv` is installed:

```bash
uv sync
```

Alternatively, create a virtual environment and install the project according to its `pyproject.toml` configuration:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install the project's dependencies using its documented dependency configuration. Do not install packages individually unless they are declared or required by the project.

### 3. Start the Backend

From the repository root:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The backend should be accessible at:

- API base URL: `http://127.0.0.1:8000`
- OpenAPI documentation: `http://127.0.0.1:8000/docs`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

Verify the health endpoint if it is registered:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 4. Start the Frontend

Open a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, normally:

`http://127.0.0.1:5173/`

The frontend API configuration must point to the running backend. Check the project's Vite configuration and environment variables if the frontend cannot connect.

### 5. Configure Ollama

Install and start Ollama, then download the configured model if it is not already available:

```powershell
ollama pull qwen3:4b
```

Verify that the model is installed:

```powershell
ollama list
```

Ensure the Ollama service is running and the backend's configured model name matches the installed model.

The core simulator and automated tests should be usable independently of a live LLM when the relevant tests use mocks.

## 🧪 Running Tests

Run the backend test suite from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest
```

Run unit tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/ -v
```

Run API tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_api.py -v
```

Run the frontend production build:

```powershell
npm --prefix frontend run build
```

The project has previously reported 299 passing backend tests and a successful frontend build. Test counts may change as the project evolves; rerun the commands to verify the current state.

## 🔐 Safety and Design Principles

NetMindAI follows these principles:

- **Simulation-first:** Disruptions affect only the in-memory simulated network.
- **Controlled execution:** LLM-generated scenario choices are validated before execution.
- **Input validation:** Model inputs must match the trained feature schema.
- **Honest reporting:** Predictions, recovery outcomes, and test results must reflect actual execution.
- **Local-first AI:** Prefer local model inference over paid external APIs.
- **Human oversight:** Disruptive recovery actions should require explicit approval in the intended response workflow.

## 🛣️ Roadmap

- [x] Local LLM integration for Red Agent scenario planning.
- [x] Controlled network link and server disruption scenarios.
- [x] In-memory topology and traffic simulation.
- [x] Telemetry and event API integration.
- [x] Standalone Random Forest inference service.
- [x] Backend–frontend connectivity and dashboard integration.
- [ ] Validated network-flow feature extraction for simulator-to-ML integration.
- [ ] Complete independent Blue Sentinel detection workflow.
- [ ] Complete Blue Response Agent with approval-gated recovery.
- [ ] End-to-end multi-agent orchestration and experiment evaluation.
- [ ] Expanded resilience metrics and repeatable scenario benchmarking.

The checklist should be updated as each feature is implemented and verified.

## 🤝 Contributing

Contributions are welcome. When extending the project:

1. Inspect existing modules and interfaces before introducing new components.
2. Preserve the separation between LLM reasoning and deterministic execution.
3. Add tests for new behavior and integration changes.
4. Never fabricate ML input features or report unverified results.
5. Avoid committing datasets, generated artifacts, local configurations, secrets, or virtual environments.
6. Document new API endpoints and configuration requirements.

## 👥 Project Information

**Project:** NetMindAI  
**Domain:** Artificial Intelligence, Cybersecurity, Computer Networking, and Machine Learning  
**Repository:** [NetMindAI on GitHub](https://github.com/Soumitra-04/NetMindAI)

## 📄 License

Add the appropriate license before redistributing or reusing this project. Until a license is selected and included in the repository, do not assume that the project is licensed for unrestricted reuse.
