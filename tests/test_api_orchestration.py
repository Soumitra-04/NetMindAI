"""Integration tests for the Orchestration API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import backend.api.simulation as sim_mod
from backend.main import app
from backend.api.orchestration import orchestrator

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_simulation_and_orchestrator(tmp_path):
    """Ensure clean simulator, telemetry, and orchestrator state before each test."""
    sim_mod.simulation = sim_mod.SimulationController.create_demo()
    sim_mod.simulation.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim_mod.simulation.telemetry.events.clear()
    orchestrator._runs.clear()


def test_api_start_run_reaches_approval():
    response = client.post(
        "/orchestration/runs",
        json={"goal": "Test API resilience", "use_llm": False},
    )
    assert response.status_code == 200
    data = response.json()

    assert "run_id" in data
    assert data["status"] == "pending_approval"
    assert data["pending_approval"] is True
    assert data["stage"] == "request_human_approval"
    assert data["recommendation_id"] is not None
    assert data["recommendation"]["action_type"] == "restore_link"
    assert data["recovery_executed"] is False

    # Verify link is disabled in simulation
    state = client.get("/simulation/state").json()
    link = next(l for l in state["topology"]["links"] if {l["source"], l["target"]} == {"router-1", "server-1"})
    assert link["active"] is False


def test_api_get_run_status():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test API get run", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]

    get_res = client.get(f"/orchestration/runs/{run_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["run_id"] == run_id
    assert data["status"] == "pending_approval"
    assert data["pending_approval"] is True


def test_api_list_runs_with_filter():
    res1 = client.post("/orchestration/runs", json={"goal": "Run 1", "use_llm": False})
    res2 = client.post("/orchestration/runs", json={"goal": "Run 2", "skip_disruption": True, "use_llm": False})

    run1_id = res1.json()["run_id"]
    run2_id = res2.json()["run_id"]

    list_res = client.get("/orchestration/runs")
    assert list_res.status_code == 200
    all_runs = list_res.json()
    assert len(all_runs) >= 2
    run_ids = [r["run_id"] for r in all_runs]
    assert run1_id in run_ids
    assert run2_id in run_ids

    # Filter by status
    pending_res = client.get("/orchestration/runs?status=pending_approval")
    assert pending_res.status_code == 200
    pending_runs = pending_res.json()
    assert all(r["status"] == "pending_approval" for r in pending_runs)
    assert run1_id in [r["run_id"] for r in pending_runs]


def test_api_approval_recovery_flow():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test approved recovery", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]
    rec_id = start_res.json()["recommendation_id"]

    # Resume with approval
    resume_res = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={
            "decision": "approve",
            "recommendation_id": rec_id,
            "approver": "secops_lead",
            "notes": "Approved for immediate recovery",
        },
    )
    assert resume_res.status_code == 200
    data = resume_res.json()

    assert data["status"] == "completed"
    assert data["pending_approval"] is False
    assert data["approval_status"] == "approved"
    assert data["recovery_executed"] is True
    assert data["verification_report"]["status"] == "verified_success"

    # Verify link active in simulation state
    state = client.get("/simulation/state").json()
    link = next(l for l in state["topology"]["links"] if {l["source"], l["target"]} == {"router-1", "server-1"})
    assert link["active"] is True

    # Check verification endpoint
    ver_res = client.get(f"/orchestration/runs/{run_id}/verification")
    assert ver_res.status_code == 200
    ver_data = ver_res.json()
    assert ver_data["status"] == "verified_success"
    assert ver_data["target_active"] is True


def test_api_rejection_flow():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test rejected recovery", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]
    rec_id = start_res.json()["recommendation_id"]

    resume_res = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={
            "decision": "reject",
            "recommendation_id": rec_id,
            "approver": "incident_commander",
            "notes": "Postpone mitigation until post-incident review",
        },
    )
    assert resume_res.status_code == 200
    data = resume_res.json()

    assert data["status"] == "rejected"
    assert data["approval_status"] == "rejected"
    assert data["recovery_executed"] is False
    assert data["recovery_result"] is None

    # Link must remain disabled
    state = client.get("/simulation/state").json()
    link = next(l for l in state["topology"]["links"] if {l["source"], l["target"]} == {"router-1", "server-1"})
    assert link["active"] is False


def test_api_resume_rejects_mismatched_recommendation_id():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test mismatch", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]

    resume_res = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={
            "decision": "approve",
            "recommendation_id": "rec-incorrect-id",
        },
    )
    assert resume_res.status_code == 400
    assert "mismatch" in resume_res.json()["detail"].lower()


def test_api_resume_rejects_invalid_decision():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test invalid decision", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]
    rec_id = start_res.json()["recommendation_id"]

    resume_res = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={
            "decision": "maybe",
            "recommendation_id": rec_id,
        },
    )
    assert resume_res.status_code == 400
    assert "invalid decision" in resume_res.json()["detail"].lower()


def test_api_duplicate_resume_rejected():
    start_res = client.post(
        "/orchestration/runs",
        json={"goal": "Test duplicate resume", "use_llm": False},
    )
    run_id = start_res.json()["run_id"]
    rec_id = start_res.json()["recommendation_id"]

    # First resume: succeeds
    res1 = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={"decision": "approve", "recommendation_id": rec_id},
    )
    assert res1.status_code == 200

    # Second resume: 400 Bad Request
    res2 = client.post(
        f"/orchestration/runs/{run_id}/resume",
        json={"decision": "approve", "recommendation_id": rec_id},
    )
    assert res2.status_code == 400
    assert "not pending approval" in res2.json()["detail"].lower()


def test_api_healthy_network_run():
    response = client.post(
        "/orchestration/runs",
        json={"goal": "Healthy audit", "skip_disruption": True, "use_llm": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed_healthy"
    assert data["pending_approval"] is False
    assert data["recovery_executed"] is False


def test_api_unknown_run_returns_404():
    res = client.get("/orchestration/runs/run-nonexistent-12345")
    assert res.status_code == 404

    res2 = client.post(
        "/orchestration/runs/run-nonexistent-12345/resume",
        json={"decision": "approve", "recommendation_id": "rec-123"},
    )
    assert res2.status_code == 404

    res3 = client.get("/orchestration/runs/run-nonexistent-12345/verification")
    assert res3.status_code == 404
