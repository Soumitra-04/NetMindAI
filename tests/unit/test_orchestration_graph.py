"""Unit tests for the NetMind LangGraph orchestration layer."""

from __future__ import annotations

from typing import Any
import pytest

from backend.agents.blue_response import BlueResponse
from backend.agents.blue_sentinel import BlueSentinel
from backend.agents.red_agent import RedAgent
from backend.network.simulation import SimulationController
from backend.orchestration.context import RuntimeContextManager
from backend.orchestration.graph import NetworkOrchestrator, build_resilience_graph
from backend.orchestration.state import OrchestrationStage, OrchestrationStatus
from backend.schemas.blue import (
    ApprovalStatus,
    DetectionStatus,
    ExecutionResult,
    RecoveryActionType,
    SentinelEvidence,
    SentinelReport,
    ValidationResult,
    VerificationReport,
    VerificationStatus,
)


class MockLLM:
    """Deterministic LLM for testing without requiring a live Ollama server."""

    model = "mock-qwen"

    def chat_json(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        num_predict: int = 150,
    ) -> dict[str, Any]:
        if "Red Agent" in system:
            return {
                "scenario_id": "link_disruption",
                "rationale": "Disrupt redundant link to test failover path.",
            }
        elif "Blue Sentinel" in system:
            return {
                "assessment": "Observable link disruption between router-1 and server-1.",
                "recommended_action": "Restore link router-1<->server-1.",
            }
        elif "Blue Response" in system:
            return {
                "action_type": "restore_link",
                "target": "router-1<->server-1",
                "reason": "Restore disabled link to normalize topology.",
                "expected_effect": "Re-enables shortest path to server-1.",
            }
        return {"scenario_id": "link_disruption", "rationale": "Default mock response"}


@pytest.fixture
def sim_env(tmp_path):
    """Isolated simulation controller and telemetry for unit testing."""
    sim = SimulationController.create_demo()
    sim.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim.telemetry.events.clear()
    return sim


@pytest.fixture
def orchestrator():
    """NetworkOrchestrator instance with fresh MemorySaver."""
    return NetworkOrchestrator()


# 1. Successful Red -> simulator -> Sentinel -> recommendation workflow
def test_full_workflow_pauses_for_approval(sim_env, orchestrator):
    state = orchestrator.start_run(
        goal="Test network resilience",
        use_llm=False,
        simulation=sim_env,
        run_id="run-test-pause",
    )

    # Must reach approval stage and pause
    assert state["status"] == OrchestrationStatus.PENDING_APPROVAL.value
    assert state["pending_approval"] is True
    assert state["stage"] == OrchestrationStage.REQUEST_HUMAN_APPROVAL.value

    # Verify disruption was executed
    assert state["disruption_result"]["status"] == "executed"
    assert state["disruption_result"]["target"] == "router-1<->server-1"
    link = next(l for l in sim_env.topology.links if {l.source, l.target} == {"router-1", "server-1"})
    assert link.active is False

    # Verify detection and recommendation were populated
    assert state["sentinel_report"]["status"] == "anomaly_detected"
    assert state["recommendation"]["action_type"] == "restore_link"
    assert state["recommendation_id"] is not None
    assert state["recovery_executed"] is False


# 2. Recovery pauses until explicit approval (simulation state unchanged before approval)
def test_recovery_pauses_until_explicit_approval(sim_env, orchestrator):
    state = orchestrator.start_run(
        goal="Test link failover",
        use_llm=False,
        simulation=sim_env,
        run_id="run-pause-check",
    )

    rec_id = state["recommendation_id"]
    assert rec_id is not None
    assert state["recovery_executed"] is False

    # Target link must remain down while awaiting approval
    link = next(l for l in sim_env.topology.links if {l.source, l.target} == {"router-1", "server-1"})
    assert link.active is False


# 3. Approved recovery executes once and reaches verification
def test_approved_recovery_executes_and_verifies(sim_env, orchestrator):
    run_id = "run-approval-exec"
    state = orchestrator.start_run(
        goal="Test full recovery",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )
    rec_id = state["recommendation_id"]

    # Resume with approval
    resumed = orchestrator.resume_run(
        run_id=run_id,
        decision="approve",
        recommendation_id=rec_id,
        approver="test_operator",
        notes="Approved for network restoration",
    )

    # Check terminal state and recovery
    assert resumed["status"] == OrchestrationStatus.COMPLETED.value
    assert resumed["stage"] == OrchestrationStage.COMPLETED.value
    assert resumed["approval_status"] == "approved"
    assert resumed["recovery_executed"] is True
    assert resumed["recovery_result"]["execution_status"] == "success"

    # Link must be restored in simulation
    link = next(l for l in sim_env.topology.links if {l.source, l.target} == {"router-1", "server-1"})
    assert link.active is True

    # Verification must be verified_success
    assert resumed["verification_report"]["status"] == VerificationStatus.VERIFIED_SUCCESS.value
    assert resumed["verification_report"]["target_active"] is True


# 4. Rejected recovery never executes
def test_rejected_recovery_never_executes(sim_env, orchestrator):
    run_id = "run-reject"
    state = orchestrator.start_run(
        goal="Test rejection",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )
    rec_id = state["recommendation_id"]

    resumed = orchestrator.resume_run(
        run_id=run_id,
        decision="reject",
        recommendation_id=rec_id,
        approver="test_operator",
        notes="Rejecting recovery per maintenance window policy",
    )

    assert resumed["status"] == OrchestrationStatus.REJECTED.value
    assert resumed["approval_status"] == "rejected"
    assert resumed["recovery_executed"] is False
    assert resumed.get("recovery_result") is None

    # Link must remain disabled
    link = next(l for l in sim_env.topology.links if {l.source, l.target} == {"router-1", "server-1"})
    assert link.active is False


# 5. Healthy network terminates without unnecessary recovery
def test_healthy_network_terminates_cleanly(sim_env, orchestrator):
    run_id = "run-healthy"
    state = orchestrator.start_run(
        goal="Audit network health",
        skip_disruption=True,
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )

    # Must complete immediately without pausing for approval
    assert state["status"] == OrchestrationStatus.COMPLETED_HEALTHY.value
    assert state["pending_approval"] is False
    assert state["sentinel_report"]["status"] == "healthy"
    assert state.get("recommendation") is None
    assert state["recovery_executed"] is False


# 6. Red Agent failure handling
def test_red_agent_planning_failure(sim_env, orchestrator):
    class FailingRedAgent(RedAgent):
        def plan(self, goal: str = "Test network resilience"):
            raise RuntimeError("Ollama connection refused")

    run_id = "run-red-fail"
    state = orchestrator.start_run(
        goal="Test resilience",
        use_llm=True,
        simulation=sim_env,
        red_agent=FailingRedAgent(sim_env),
        run_id=run_id,
    )

    assert state["status"] == OrchestrationStatus.FAILED.value
    assert state["failure_stage"] == OrchestrationStage.PLAN_DISRUPTION.value
    assert "Red Agent planning failed" in state["error"]


def test_red_agent_execution_failure(sim_env, orchestrator):
    # Disable link beforehand so RedAgent.execute raises RuntimeError
    sim_env.topology.set_link_status("router-1", "server-1", active=False)

    run_id = "run-red-exec-fail"
    state = orchestrator.start_run(
        goal="Test resilience",
        scenario_id="link_disruption",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )

    assert state["status"] == OrchestrationStatus.FAILED.value
    assert state["failure_stage"] == OrchestrationStage.EXECUTE_DISRUPTION.value
    assert "already disabled" in state["error"]


# 7. Sentinel failure or invalid detection result
def test_sentinel_failure_handling(sim_env, orchestrator):
    class FailingSentinel(BlueSentinel):
        def detect(self, *args, **kwargs):
            raise RuntimeError("Telemetry ingestion pipeline failure")

    run_id = "run-sentinel-fail"
    state = orchestrator.start_run(
        goal="Test sentinel failure",
        scenario_id="link_disruption",
        use_llm=False,
        simulation=sim_env,
        sentinel=FailingSentinel(sim_env),
        run_id=run_id,
    )

    assert state["status"] == OrchestrationStatus.FAILED.value
    assert state["failure_stage"] == OrchestrationStage.DETECT_ANOMALY.value
    assert "Blue Sentinel detection failed" in state["error"]


# 8. Invalid / stale recommendation handling
def test_stale_recommendation_rejected_on_approval(sim_env, orchestrator):
    run_id = "run-stale-rec"
    state = orchestrator.start_run(
        goal="Test stale recommendation",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )
    rec_id = state["recommendation_id"]

    # External manual reactivation of the link before operator resumes
    sim_env.topology.set_link_status("router-1", "server-1", active=True)

    # Resuming should fail because the recommendation is now stale
    resumed = orchestrator.resume_run(
        run_id=run_id,
        decision="approve",
        recommendation_id=rec_id,
    )

    assert resumed["status"] == OrchestrationStatus.FAILED.value
    assert resumed["failure_stage"] == OrchestrationStage.REQUEST_HUMAN_APPROVAL.value
    assert "stale" in resumed["error"].lower() or "no longer valid" in resumed["error"].lower()


# 9. Verification failure is not reported as success
def test_verification_failure_not_reported_as_success(sim_env, orchestrator):
    run_id = "run-verif-fail"
    state = orchestrator.start_run(
        goal="Test verification failure",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )
    rec_id = state["recommendation_id"]

    from backend.orchestration.context import runtime_context_manager
    ctx = runtime_context_manager.get_context(run_id)
    old_resp = ctx.blue_response

    class MockFailingResponse(BlueResponse):
        def execute_approved(self, recommendation_id: str):
            res = super().execute_approved(recommendation_id)
            # Override verification to failure
            res.verification = VerificationReport(
                status=VerificationStatus.VERIFICATION_FAILED,
                target_active=False,
                route_after=None,
                reachable_flows=0,
                details={"simulated": "failure"},
            )
            return res

    mock_resp = MockFailingResponse(sim_env)
    mock_resp.recommendations = old_resp.recommendations
    ctx.blue_response = mock_resp

    resumed = orchestrator.resume_run(
        run_id=run_id,
        decision="approve",
        recommendation_id=rec_id,
    )

    assert resumed["status"] == OrchestrationStatus.VERIFICATION_FAILED.value
    assert resumed["status"] != OrchestrationStatus.COMPLETED.value
    assert resumed["failure_stage"] == OrchestrationStage.VERIFY_RECOVERY.value


# 10. Resume uses correct run and recommendation ID
def test_resume_validates_recommendation_id(sim_env, orchestrator):
    run_id = "run-rec-id-val"
    state = orchestrator.start_run(
        goal="Test rec ID check",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )

    # Resume with wrong recommendation ID
    with pytest.raises(ValueError, match="Recommendation ID mismatch"):
        orchestrator.resume_run(
            run_id=run_id,
            decision="approve",
            recommendation_id="rec-wrong-9999",
        )

    # Resume with non-existent run ID
    with pytest.raises(KeyError, match="not found"):
        orchestrator.resume_run(
            run_id="run-nonexistent",
            decision="approve",
            recommendation_id="rec-123",
        )


# 11. Duplicate resume cannot duplicate state-changing recovery action
def test_duplicate_resume_rejected(sim_env, orchestrator):
    run_id = "run-dup-resume"
    state = orchestrator.start_run(
        goal="Test duplicate resume",
        use_llm=False,
        simulation=sim_env,
        run_id=run_id,
    )
    rec_id = state["recommendation_id"]

    # First resume: succeeds
    res1 = orchestrator.resume_run(
        run_id=run_id,
        decision="approve",
        recommendation_id=rec_id,
    )
    assert res1["status"] == OrchestrationStatus.COMPLETED.value

    # Second resume attempt on the same run: must be rejected
    with pytest.raises(RuntimeError, match="is not pending approval"):
        orchestrator.resume_run(
            run_id=run_id,
            decision="approve",
            recommendation_id=rec_id,
        )


# 12. Bounded execution and safe termination
def test_iteration_bounds_enforced(sim_env):
    from backend.orchestration.graph import build_resilience_graph

    graph = build_resilience_graph()
    run_id = "run-iter-bounds"

    # Start with iteration count exceeding maximum
    state = {
        "run_id": run_id,
        "goal": "Test bounds",
        "iteration_count": 10,
        "max_iterations": 5,
        "status": OrchestrationStatus.RUNNING.value,
        "stage": OrchestrationStage.PLAN_DISRUPTION.value,
    }

    config = {"configurable": {"thread_id": run_id}}
    result = graph.invoke(state, config=config)

    assert result["status"] == OrchestrationStatus.FAILED.value
    assert "bounds" in result["error"].lower()
    assert result["stage"] == OrchestrationStage.COMPLETED.value
