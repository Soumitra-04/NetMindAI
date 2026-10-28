
import pytest

from backend.agents.red_agent import RedAgent
from backend.network.simulation import SimulationController


@pytest.fixture
def simulation(tmp_path):
    simulation = SimulationController.create_demo()

    # Isolate telemetry for each test instead of reading the
    # persistent data/events.jsonl from previous runs.
    simulation.telemetry.event_log_path = tmp_path / "events.jsonl"
    simulation.telemetry.events.clear()

    return simulation


def test_red_agent_disables_target_link(simulation):
    agent = RedAgent(simulation)

    result = agent.execute("link_disruption")

    assert result["status"] == "executed"
    assert result["disruption_active"] is True

    # The simulator already uses its redundant, lower-latency route.
    assert result["route_before"] == [
        "client-1",
        "switch-1",
        "server-1",
    ]

    # Disabling the router link should not break the redundant route.
    assert result["route_after"] == [
        "client-1",
        "switch-1",
        "server-1",
    ]

    link = next(
        link
        for link in simulation.topology.links
        if {link.source, link.target} == {"router-1", "server-1"}
    )
    assert link.active is False


def test_red_agent_records_telemetry(simulation):
    agent = RedAgent(simulation)

    result = agent.execute()

    events = simulation.telemetry.get_events(
        limit=10,
        event_type="red_scenario_executed",
    )

    assert len(events) == 1
    assert events[0]["source"] == "red_agent"
    assert events[0]["details"]["scenario_id"] == result["scenario_id"]


def test_red_agent_rejects_unknown_scenario(simulation):
    agent = RedAgent(simulation)

    with pytest.raises(ValueError, match="Unsupported scenario"):
        agent.execute("unknown_scenario")


def test_red_agent_rejects_already_disabled_link(simulation):
    simulation.topology.set_link_status(
        "router-1", "server-1", active=False
    )
    agent = RedAgent(simulation)

    with pytest.raises(RuntimeError, match="already disabled"):
        agent.execute("link_disruption")



def test_red_agent_uses_llm_plan(simulation):
    import json
    from backend.agents.red_agent import RedAgent

    class FakeLLM:
        model = "test-model"

        def chat_json(self, system, prompt):
            request = json.loads(prompt)

            assert "network_summary" in request
            assert "link_disruption" in request["allowed_scenario_ids"]
            assert "server_disruption" in request["allowed_scenario_ids"]

            return {
                "scenario_id": "link_disruption",
                "rationale": (
                    "Test whether the redundant path preserves connectivity."
                ),
            }

    agent = RedAgent(simulation, llm=FakeLLM())
    plan = agent.plan()

    assert plan["scenario_id"] == "link_disruption"
    assert "redundant path" in plan["rationale"].lower()
    assert plan["planner_model"] == "test-model"


def test_red_agent_rejects_invalid_llm_plan(simulation):
    from backend.agents.red_agent import RedAgent

    class FakeLLM:
        model = "test-model"

        def chat_json(self, system, prompt):
            return {
                "scenario_id": "run_external_attack",
                "rationale": "This scenario is not permitted.",
            }

    agent = RedAgent(simulation, llm=FakeLLM())

    with pytest.raises(ValueError, match="unsupported scenario"):
        agent.plan()



def test_red_agent_executes_server_disruption(simulation):
    agent = RedAgent(simulation)

    result = agent.execute("server_disruption")

    assert result["scenario_id"] == "server_disruption"
    assert result["status"] == "executed"
    assert result["action"] == "disable_simulated_node"
    assert result["target"] == "server-1"
    assert result["route_before"] == ["client-1", "switch-1", "server-1"]
    assert result["route_after"] is None
    assert result["disruption_active"] is True

    # Check node status in topology
    server = simulation.topology.get_node("server-1")
    assert server.active is False

    # Check telemetry event recorded
    events = simulation.telemetry.get_events(
        limit=10,
        event_type="red_scenario_executed",
    )
    assert len(events) == 1
    assert events[0]["source"] == "red_agent"
    assert events[0]["entity_id"] == "server-1"
    assert "unreachable" in events[0]["message"]


def test_red_agent_rejects_already_disabled_server(simulation):
    simulation.topology.set_node_status("server-1", active=False)
    agent = RedAgent(simulation)

    with pytest.raises(RuntimeError, match="Target server is already disabled"):
        agent.execute("server_disruption")


def test_red_agent_rejects_empty_or_whitespace_goal(simulation):
    agent = RedAgent(simulation)

    with pytest.raises(ValueError, match="Planning goal cannot be empty"):
        agent.plan("")

    with pytest.raises(ValueError, match="Planning goal cannot be empty"):
        agent.plan("   \t\n  ")


def test_red_agent_executes_planned_workflow(simulation):
    class FakeLLM:
        model = "mock-qwen"

        def chat_json(self, system, prompt):
            return {
                "scenario_id": "server_disruption",
                "rationale": "Target server-1 to evaluate traffic isolation.",
            }

    agent = RedAgent(simulation, llm=FakeLLM())
    result = agent.execute_planned(goal="Test server failure")

    assert result["scenario_id"] == "server_disruption"
    assert result["status"] == "executed"
    assert result["plan"]["scenario_id"] == "server_disruption"
    assert result["plan"]["planner_model"] == "mock-qwen"
    assert result["plan"]["rationale"] == "Target server-1 to evaluate traffic isolation."

    # Topology should reflect node is down
    assert simulation.topology.get_node("server-1").active is False


def test_red_agent_handles_unavailable_ollama(simulation):
    class FailingLLM:
        model = "failing-model"

        def chat_json(self, system, prompt):
            raise RuntimeError("Cannot connect to Ollama at http://localhost:11434. Is Ollama running?")

    agent = RedAgent(simulation, llm=FailingLLM())

    with pytest.raises(RuntimeError, match="Cannot connect to Ollama"):
        agent.plan()


def test_red_agent_handles_malformed_llm_response(simulation):
    class MalformedLLM:
        model = "malformed-model"

        def __init__(self, bad_payload):
            self.bad_payload = bad_payload

        def chat_json(self, system, prompt):
            return self.bad_payload

    # Missing rationale
    agent1 = RedAgent(simulation, llm=MalformedLLM({"scenario_id": "link_disruption"}))
    with pytest.raises(ValueError, match="must include a rationale"):
        agent1.plan()

    # Empty rationale
    agent2 = RedAgent(simulation, llm=MalformedLLM({"scenario_id": "link_disruption", "rationale": "  "}))
    with pytest.raises(ValueError, match="must include a rationale"):
        agent2.plan()

    # Missing scenario_id
    agent3 = RedAgent(simulation, llm=MalformedLLM({"rationale": "Valid reason"}))
    with pytest.raises(ValueError, match="unsupported scenario"):
        agent3.plan()


def test_red_agent_state_changes_visible_in_snapshot(simulation):
    agent = RedAgent(simulation)
    agent.execute("server_disruption")

    # Step simulation so traffic engine and telemetry update
    snapshot = simulation.step()

    # Check topology in snapshot
    server_node = next(
        n for n in snapshot["topology"]["nodes"] if n["id"] == "server-1"
    )
    assert server_node["active"] is False

    # Check flow destined for server-1
    flow1 = next(f for f in snapshot["flows"] if f["id"] == "flow-1")
    assert flow1["reachable"] is False
    assert flow1["route"] is None

    # Check metrics
    traffic_metrics = snapshot["metrics"]["traffic"]
    assert traffic_metrics["reachable_active_flows"] == 1
    assert traffic_metrics["total_flows"] == 2
