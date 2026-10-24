
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
