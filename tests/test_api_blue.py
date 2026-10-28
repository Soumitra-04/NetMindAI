"""Integration tests for Blue Agent API endpoints."""

from fastapi.testclient import TestClient
import pytest

from backend.main import app
import backend.api.simulation as sim_mod

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_simulation(tmp_path):
    sim_mod.simulation = sim_mod.SimulationController.create_demo()
    sim_mod.simulation.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim_mod.simulation.telemetry.events.clear()
    import backend.api.blue as blue_mod
    blue_mod.response_agent.recommendations.clear()


def test_api_sentinel_detect_healthy():
    response = client.post("/blue/sentinel/detect?use_llm=false")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert len(data["affected_nodes"]) == 0
    assert len(data["affected_links"]) == 0


def test_api_sentinel_detect_anomaly():
    sim_mod.simulation.topology.set_link_status("router-1", "server-1", active=False)

    response = client.post("/blue/sentinel/detect?use_llm=false")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "anomaly_detected"
    assert "router-1<->server-1" in data["affected_links"]


def test_api_response_workflow_link_recovery():
    # 1. Simulate disruption
    sim_mod.simulation.topology.set_link_status("router-1", "server-1", active=False)

    # 2. Request recommendation
    rec_res = client.post("/blue/response/recommend?use_llm=false")
    assert rec_res.status_code == 200
    rec = rec_res.json()
    rec_id = rec["recommendation_id"]
    assert rec["action_type"] == "restore_link"
    assert rec["target"] == "router-1<->server-1"
    assert rec["approval_status"] == "pending"

    # 3. List recommendations
    list_res = client.get("/blue/response/recommendations")
    assert list_res.status_code == 200
    assert any(r["recommendation_id"] == rec_id for r in list_res.json())

    # 4. Get single recommendation
    get_res = client.get(f"/blue/response/recommendations/{rec_id}")
    assert get_res.status_code == 200
    assert get_res.json()["recommendation_id"] == rec_id

    # 5. Attempt execution BEFORE approval -> 403 Forbidden
    exec_blocked = client.post(f"/blue/response/recommendations/{rec_id}/execute")
    assert exec_blocked.status_code == 403
    assert "requires explicit approval" in exec_blocked.json()["detail"]

    # 6. Approve recommendation
    approve_res = client.post(
        f"/blue/response/recommendations/{rec_id}/approve",
        json={"approver": "secops_analyst", "notes": "Approved link restoration"},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["approval_status"] == "approved"

    # 7. Execute approved recommendation
    exec_res = client.post(f"/blue/response/recommendations/{rec_id}/execute")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["execution_status"] == "success"
    assert exec_data["verification"]["status"] == "verified_success"
    assert exec_data["verification"]["target_active"] is True

    # 8. Check verification endpoint
    ver_res = client.get(f"/blue/response/recommendations/{rec_id}/verification")
    assert ver_res.status_code == 200
    assert ver_res.json()["status"] == "verified_success"

    # 9. Verify link active in simulation state
    state = client.get("/simulation/state").json()
    link = next(l for l in state["topology"]["links"] if {l["source"], l["target"]} == {"router-1", "server-1"})
    assert link["active"] is True


def test_api_rejection_workflow():
    sim_mod.simulation.topology.set_node_status("server-1", active=False)

    rec_res = client.post("/blue/response/recommend?use_llm=false")
    rec_id = rec_res.json()["recommendation_id"]

    # Reject
    reject_res = client.post(
        f"/blue/response/recommendations/{rec_id}/reject",
        json={"approver": "lead_engineer", "reason": "Will replace hardware instead"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["approval_status"] == "rejected"

    # Execution must still be blocked (403)
    exec_res = client.post(f"/blue/response/recommendations/{rec_id}/execute")
    assert exec_res.status_code == 403


def test_api_recommendation_not_found():
    res = client.get("/blue/response/recommendations/rec-nonexistent")
    assert res.status_code == 404

    res2 = client.post("/blue/response/recommendations/rec-nonexistent/approve")
    assert res2.status_code == 404

    res3 = client.post("/blue/response/recommendations/rec-nonexistent/execute")
    assert res3.status_code == 404
