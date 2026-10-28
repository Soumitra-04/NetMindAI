"""Unit tests for the Blue Sentinel independent detection agent."""

import pytest

from backend.agents.blue_sentinel import BlueSentinel
from backend.network.simulation import SimulationController
from backend.schemas.blue import DetectionStatus


@pytest.fixture
def simulation(tmp_path):
    sim = SimulationController.create_demo()
    sim.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim.telemetry.events.clear()
    return sim


def test_sentinel_detects_healthy_state(simulation):
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    assert report.status == DetectionStatus.HEALTHY
    assert report.severity == "info"
    assert report.confidence == 1.0
    assert len(report.affected_nodes) == 0
    assert len(report.affected_links) == 0
    assert len(report.affected_flows) == 0
    assert "No recovery action required" in report.recommended_action
    assert report.model_inference.status == "unavailable"


def test_sentinel_detects_link_disruption(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)

    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    assert report.status == DetectionStatus.ANOMALY_DETECTED
    assert "router-1<->server-1" in report.affected_links
    assert report.severity == "warning"
    assert report.confidence == 1.0
    assert any("router-1<->server-1" in f for f in report.findings)
    assert "Restore disabled link router-1<->server-1" in report.recommended_action


def test_sentinel_detects_server_disruption_and_unreachable_flows(simulation):
    simulation.topology.set_node_status("server-1", active=False)
    # Advance simulation so flow-1 reachability state updates
    simulation.step()

    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    assert report.status == DetectionStatus.ANOMALY_DETECTED
    assert "server-1" in report.affected_nodes
    assert "flow-1" in report.affected_flows
    assert report.severity == "critical"
    assert any("server-1" in f for f in report.findings)
    assert any("flow-1" in f for f in report.findings)
    assert "Reactivate disabled node server-1" in report.recommended_action


def test_sentinel_independent_from_red_agent_event(simulation):
    # Context 1: Link is disabled without any Red Agent event in telemetry
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)
    assert report.status == DetectionStatus.ANOMALY_DETECTED
    assert "router-1<->server-1" in report.affected_links

    # Context 2: Red Agent event exists in telemetry, but network is actually healthy
    simulation.topology.set_link_status("router-1", "server-1", active=True)
    simulation.telemetry.record_event(
        event_type="red_scenario_executed",
        message="Stale red agent execution",
        severity="warning",
        source="red_agent",
        details={"scenario_id": "link_disruption"},
    )

    report2 = sentinel.detect(use_llm=False)
    # Must report HEALTHY based on actual observable network state, not blindly trust red event
    assert report2.status == DetectionStatus.HEALTHY
    assert len(report2.affected_links) == 0
    assert any(e["source"] == "red_agent" for e in report2.evidence.contextual_events)


def test_sentinel_ml_unavailable_without_features(simulation):
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(flow_features=None, use_llm=False)

    assert report.model_inference.status == "unavailable"
    assert "67 CICIDS" in report.model_inference.reason
    assert report.model_inference.result is None
    # Detection still works
    assert report.status == DetectionStatus.HEALTHY


def test_sentinel_ml_evaluation_when_features_provided(simulation):
    class MockInferenceService:
        threshold = 0.3065

        def predict(self, features):
            return {
                "prediction": 1,
                "label": "ATTACK",
                "attack_probability": 0.8521,
                "threshold": 0.3065,
                "model_metadata": {"model_name": "MockForest"},
            }

    sentinel = BlueSentinel(simulation, inference_service=MockInferenceService())
    dummy_features = {"feature_1": 1.0}
    report = sentinel.detect(flow_features=dummy_features, use_llm=False)

    assert report.model_inference.status == "completed"
    assert report.model_inference.result["prediction"] == 1
    assert any("[ML Finding]" in f for f in report.findings)
    assert report.status == DetectionStatus.INVESTIGATION_REQUIRED


def test_sentinel_handles_ml_failure_gracefully(simulation):
    class FaultyInferenceService:
        threshold = 0.3065

        def predict(self, features):
            raise ValueError("Corrupt feature vector")

    sentinel = BlueSentinel(simulation, inference_service=FaultyInferenceService())
    report = sentinel.detect(flow_features={"bad": "data"}, use_llm=False)

    assert report.model_inference.status == "error"
    assert "Corrupt feature vector" in report.model_inference.reason
    assert any("ML inference evaluation failed" in err for err in report.errors_or_limitations)
    # Overall detection still functions
    assert report.status == DetectionStatus.HEALTHY


def test_sentinel_with_mocked_llm(simulation):
    class MockLLM:
        model = "mock-qwen3"

        def chat_json(self, system, prompt, schema=None, num_predict=150):
            return {
                "assessment": "Critical link disruption detected on router-1 to server-1 path.",
                "recommended_action": "Execute path failover to restore connectivity.",
            }

    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation, llm=MockLLM())
    report = sentinel.detect(use_llm=True)

    assert report.status == DetectionStatus.ANOMALY_DETECTED
    assert any("[LLM Assessment]" in f for f in report.findings)
    assert "Critical link disruption" in report.findings[-1]
    assert report.recommended_action == "Execute path failover to restore connectivity."


def test_sentinel_handles_unavailable_llm_gracefully(simulation):
    class FailingLLM:
        model = "failing-qwen"

        def chat_json(self, system, prompt, schema=None, num_predict=150):
            raise RuntimeError("Cannot connect to Ollama at http://localhost:11434. Is Ollama running?")

    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation, llm=FailingLLM())
    report = sentinel.detect(use_llm=True)

    # Core detection succeeds deterministically
    assert report.status == DetectionStatus.ANOMALY_DETECTED
    assert "router-1<->server-1" in report.affected_links
    assert any("LLM evidence interpretation omitted" in err for err in report.errors_or_limitations)
