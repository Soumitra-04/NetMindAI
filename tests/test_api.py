
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.simulation import simulation

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_topology_endpoint():
    response = client.get("/topology/")

    assert response.status_code == 200

    data = response.json()
    assert data
    assert len(data["nodes"]) == 6


def test_simulation_state_endpoint():
    response = client.get("/simulation/state")

    assert response.status_code == 200

    data = response.json()
    assert data["step_number"] == 0
    assert "topology" in data
    assert "flows" in data
    assert "metrics" in data


def test_simulation_step_endpoint():
    response = client.post("/simulation/reset")
    assert response.status_code == 200

    first = client.post("/simulation/step")
    second = client.post("/simulation/step")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["step_number"] == 1
    assert second.json()["step_number"] == 2


def test_simulation_reset_endpoint():
    client.post("/simulation/step")

    response = client.post("/simulation/reset")

    assert response.status_code == 200
    assert response.json()["step_number"] == 0
    assert len(response.json()["flows"]) == 2


def test_reset_restores_demo_topology_and_flows():
    client.post("/simulation/reset")

    initial = client.get("/simulation/state").json()
    original_node_count = len(initial["topology"]["nodes"])
    original_flow_count = len(initial["flows"])

    client.post("/simulation/step")
    reset = client.post("/simulation/reset")

    assert reset.status_code == 200

    state = client.get("/simulation/state").json()

    assert state["step_number"] == 0
    assert len(state["topology"]["nodes"]) == original_node_count
    assert len(state["flows"]) == original_flow_count


def test_events_endpoint_returns_list():
    response = client.get("/events/")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_events_endpoint_reflects_red_agent_execution(tmp_path):
    from backend.agents.red_agent import RedAgent
    import backend.api.simulation as sim_mod

    sim_mod.simulation = sim_mod.SimulationController.create_demo()
    sim_mod.simulation.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim_mod.simulation.telemetry.events.clear()

    agent = RedAgent(sim_mod.simulation)
    result = agent.execute("link_disruption")

    response = client.get("/events/?event_type=red_scenario_executed")
    assert response.status_code == 200

    events = response.json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "red_scenario_executed"
    assert events[0]["source"] == "red_agent"
    assert events[0]["details"]["scenario_id"] == "link_disruption"

    # Verify simulation state reflects disruption
    state_res = client.get("/simulation/state")
    assert state_res.status_code == 200
    state = state_res.json()
    # Check that router-1<->server-1 link is disabled
    link = next(
        l for l in state["topology"]["links"]
        if {l["source"], l["target"]} == {"router-1", "server-1"}
    )
    assert link["active"] is False


def test_events_endpoint_filters_by_severity_and_type(tmp_path):
    import backend.api.simulation as sim_mod

    sim_mod.simulation = sim_mod.SimulationController.create_demo()
    sim_mod.simulation.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim_mod.simulation.telemetry.events.clear()

    sim_mod.simulation.telemetry.record_event(
        event_type="test_info",
        message="Info event",
        severity="info",
    )
    sim_mod.simulation.telemetry.record_event(
        event_type="test_warn",
        message="Warning event",
        severity="warning",
    )

    info_res = client.get("/events/?severity=info")
    assert info_res.status_code == 200
    info_events = info_res.json()
    assert len(info_events) == 1
    assert info_events[0]["event_type"] == "test_info"

    warn_res = client.get("/events/?severity=warning")
    assert warn_res.status_code == 200
    warn_events = warn_res.json()
    assert len(warn_events) == 1
    assert warn_events[0]["event_type"] == "test_warn"


def test_events_endpoint_rejects_invalid_severity():
    response = client.get("/events/?severity=not_a_real_severity")
    assert response.status_code == 400


def test_cors_preflight_options():
    endpoints = [
        "/health",
        "/simulation/state",
        "/events/?limit=15",
        "/orchestration/runs",
        "/topology/",
    ]
    for ep in endpoints:
        response = client.options(
            ep,
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200, f"Failed preflight for {ep}"
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
        assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_cors_get_headers():
    response = client.get(
        "/simulation/state",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_topology_and_events_trailing_slash_flexibility():
    top_no_slash = client.get("/topology")
    top_slash = client.get("/topology/")
    assert top_no_slash.status_code == 200
    assert top_slash.status_code == 200
    assert top_no_slash.json() == top_slash.json()

    ev_no_slash = client.get("/events")
    ev_slash = client.get("/events/")
    assert ev_no_slash.status_code == 200
    assert ev_slash.status_code == 200
