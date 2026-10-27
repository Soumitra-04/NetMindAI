
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

