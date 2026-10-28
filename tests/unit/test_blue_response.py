"""Unit tests for the Blue Response safe recovery agent."""

import pytest

from backend.agents.blue_response import BlueResponse
from backend.agents.blue_sentinel import BlueSentinel
from backend.network.simulation import SimulationController
from backend.schemas.blue import (
    ApprovalStatus,
    DetectionStatus,
    RecoveryActionType,
    VerificationStatus,
)


@pytest.fixture
def simulation(tmp_path):
    sim = SimulationController.create_demo()
    sim.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim.telemetry.events.clear()
    return sim


def test_response_recommends_no_action_for_healthy_network(simulation):
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    assert rec.action_type == RecoveryActionType.NO_ACTION
    assert rec.target is None
    assert rec.approval_required is False
    assert rec.approval_status == ApprovalStatus.APPROVED
    assert rec.validation_result.valid is True
    assert "healthy" in rec.reason.lower()


def test_response_recommends_restore_link_for_link_disruption(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    assert rec.action_type == RecoveryActionType.RESTORE_LINK
    assert rec.target == "router-1<->server-1"
    assert rec.approval_required is True
    assert rec.approval_status == ApprovalStatus.PENDING
    assert rec.validation_result.valid is True


def test_response_recommends_restore_node_for_server_disruption(simulation):
    simulation.topology.set_node_status("server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    assert rec.action_type == RecoveryActionType.RESTORE_NODE
    assert rec.target == "server-1"
    assert rec.approval_required is True
    assert rec.approval_status == ApprovalStatus.PENDING
    assert rec.validation_result.valid is True


def test_response_uses_mocked_llm_for_recommendation(simulation):
    class MockLLM:
        model = "mock-qwen"

        def chat_json(self, system, prompt, schema=None, num_predict=150):
            return {
                "action_type": "restore_link",
                "target": "router-1<->server-1",
                "reason": "Re-enable primary redundant trunk to eliminate rerouting latency.",
                "expected_effect": "Direct traffic restored between router-1 and server-1.",
            }

    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation, llm=MockLLM())
    rec = response_agent.recommend(report, use_llm=True)

    assert rec.action_type == RecoveryActionType.RESTORE_LINK
    assert rec.target == "router-1<->server-1"
    assert "redundant trunk" in rec.reason
    assert rec.validation_result.valid is True


def test_response_rejects_invalid_llm_action_and_falls_back(simulation):
    class MaliciousOrInvalidLLM:
        model = "bad-qwen"

        def chat_json(self, system, prompt, schema=None, num_predict=150):
            # Propose an unauthorized / non-allowlisted action
            return {
                "action_type": "wipe_firewall_rules",
                "target": "firewall-1",
                "reason": "Clear all filters.",
                "expected_effect": "Total bypass.",
            }

    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation, llm=MaliciousOrInvalidLLM())
    rec = response_agent.recommend(report, use_llm=True)

    # Must reject LLM action and fall back to safe deterministic restore_link
    assert rec.action_type == RecoveryActionType.RESTORE_LINK
    assert rec.target == "router-1<->server-1"
    assert rec.validation_result.valid is True


def test_unapproved_execution_rejected(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    with pytest.raises(PermissionError, match="requires explicit approval"):
        response_agent.execute_approved(rec.recommendation_id)


def test_rejected_recommendation_cannot_be_executed(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    # Explicit rejection
    rejected = response_agent.reject_recommendation(
        rec.recommendation_id,
        approver="secops_lead",
        reason="Scheduled maintenance window preferred.",
    )
    assert rejected.approval_status == ApprovalStatus.REJECTED

    with pytest.raises(PermissionError, match="requires explicit approval"):
        response_agent.execute_approved(rec.recommendation_id)


def test_approve_and_execute_recovery_link(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    # Approve
    approved = response_agent.approve_recommendation(
        rec.recommendation_id,
        approver="admin_alice",
        notes="Authorized failback recovery.",
    )
    assert approved.approval_status == ApprovalStatus.APPROVED
    assert approved.approver == "admin_alice"

    # Execute
    res = response_agent.execute_approved(rec.recommendation_id)
    assert res.execution_status == "success"
    assert res.verification.status == VerificationStatus.VERIFIED_SUCCESS
    assert res.verification.target_active is True

    # Confirm link active in topology
    link = next(l for l in simulation.topology.links if {l.source, l.target} == {"router-1", "server-1"})
    assert link.active is True


def test_approve_and_execute_recovery_server(simulation):
    simulation.topology.set_node_status("server-1", active=False)
    simulation.step()
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)

    approved = response_agent.approve_recommendation(rec.recommendation_id)
    res = response_agent.execute_approved(rec.recommendation_id)

    assert res.execution_status == "success"
    assert res.verification.status == VerificationStatus.VERIFIED_SUCCESS
    assert res.verification.target_active is True

    # Confirm node active in topology
    server = simulation.topology.get_node("server-1")
    assert server.active is True


def test_stale_recommendation_aborted(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)
    response_agent.approve_recommendation(rec.recommendation_id)

    # Out-of-band state change makes recommendation stale
    simulation.topology.set_link_status("router-1", "server-1", active=True)

    with pytest.raises(RuntimeError, match="failed pre-execution validation"):
        response_agent.execute_approved(rec.recommendation_id)

    assert rec.approval_status == ApprovalStatus.CANCELLED


def test_repeated_execution_blocked(simulation):
    simulation.topology.set_link_status("router-1", "server-1", active=False)
    sentinel = BlueSentinel(simulation)
    report = sentinel.detect(use_llm=False)

    response_agent = BlueResponse(simulation)
    rec = response_agent.recommend(report, use_llm=False)
    response_agent.approve_recommendation(rec.recommendation_id)
    response_agent.execute_approved(rec.recommendation_id)

    with pytest.raises(PermissionError, match="requires explicit approval"):
        response_agent.execute_approved(rec.recommendation_id)


def test_unknown_recommendation_id_rejected(simulation):
    response_agent = BlueResponse(simulation)

    with pytest.raises(KeyError, match="not found"):
        response_agent.get_recommendation("rec-nonexistent")

    with pytest.raises(KeyError, match="not found"):
        response_agent.approve_recommendation("rec-nonexistent")

    with pytest.raises(KeyError, match="not found"):
        response_agent.execute_approved("rec-nonexistent")


def test_action_validation_rejects_invalid_target_and_action(simulation):
    response_agent = BlueResponse(simulation)

    # Unknown action type
    val1 = response_agent.validate_action("delete_database", "server-1")
    assert val1.valid is False
    assert any("Unsupported action type" in e for e in val1.errors)

    # Unknown node
    val2 = response_agent.validate_action(RecoveryActionType.RESTORE_NODE, "server-999")
    assert val2.valid is False
    assert any("does not exist" in e for e in val2.errors)

    # Already active node
    val3 = response_agent.validate_action(RecoveryActionType.RESTORE_NODE, "server-1")
    assert val3.valid is False
    assert any("already active" in e for e in val3.errors)

    # Unknown link
    val4 = response_agent.validate_action(RecoveryActionType.RESTORE_LINK, "client-1<->server-1")
    assert val4.valid is False
    assert any("does not exist" in e for e in val4.errors)


def test_list_recommendations_filtering(simulation):
    response_agent = BlueResponse(simulation)

    rec1 = response_agent.recommend(
        {"detection_id": "d1", "status": "anomaly_detected", "affected_links": ["router-1<->server-1"], "affected_nodes": [], "findings": ["link down"], "recommended_action": "restore", "model_inference": {"status": "unavailable"}},
        use_llm=False,
    )
    rec2 = response_agent.recommend(
        {"detection_id": "d2", "status": "healthy", "affected_links": [], "affected_nodes": [], "findings": ["all good"], "recommended_action": "none", "model_inference": {"status": "unavailable"}},
        use_llm=False,
    )

    all_recs = response_agent.list_recommendations()
    assert len(all_recs) == 2

    pending_recs = response_agent.list_recommendations(status="pending")
    assert len(pending_recs) == 1
    assert pending_recs[0].recommendation_id == rec1.recommendation_id

    approved_recs = response_agent.list_recommendations(status="approved")
    assert len(approved_recs) == 1
    assert approved_recs[0].recommendation_id == rec2.recommendation_id
