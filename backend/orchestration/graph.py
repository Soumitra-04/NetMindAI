"""LangGraph Orchestration Layer for NetMind Resilience Coordination.

Coordinates Red Agent disruption, independent Blue Sentinel detection,
Blue Response mitigation planning, explicit human approval gating,
and post-recovery verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from backend.network.simulation import SimulationController
from backend.orchestration.context import runtime_context_manager
from backend.orchestration.state import (
    OrchestrationStage,
    OrchestrationState,
    OrchestrationStatus,
)
from backend.schemas.blue import (
    ApprovalStatus,
    DetectionStatus,
    RecoveryActionType,
    VerificationStatus,
)


# -----------------------------------------------------------------------------
# Node Implementations
# -----------------------------------------------------------------------------


def initialize_run(state: OrchestrationState) -> dict[str, Any]:
    """Initialize run metadata, validate goal, and record startup telemetry."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state.get("run_id") or f"run-{uuid4().hex[:8]}"
    goal = (state.get("goal") or "Test network resilience").strip()

    iter_count = state.get("iteration_count", 0)
    max_iters = state.get("max_iterations", 5)
    if iter_count > max_iters:
        return {
            "run_id": run_id,
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.INITIALIZED.value,
            "failure_stage": OrchestrationStage.INITIALIZED.value,
            "error": f"Max iteration bounds ({max_iters}) exceeded.",
            "updated_at": now,
        }

    if not goal:
        return {
            "run_id": run_id,
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.INITIALIZED.value,
            "error": "Goal cannot be empty.",
            "failure_stage": OrchestrationStage.INITIALIZED.value,
            "updated_at": now,
        }

    ctx = runtime_context_manager.get_context(run_id)
    try:
        ctx.simulation.telemetry.record_event(
            event_type="orchestration_run_started",
            message=f"Orchestration run {run_id} started with goal: {goal!r}",
            severity="info",
            source="orchestrator",
            entity_id=run_id,
            details={"goal": goal, "skip_disruption": state.get("skip_disruption", False)},
        )
    except Exception:
        pass

    return {
        "run_id": run_id,
        "goal": goal,
        "status": OrchestrationStatus.RUNNING.value,
        "stage": OrchestrationStage.INITIALIZED.value,
        "iteration_count": iter_count,
        "max_iterations": max_iters,
        "recovery_executed": False,
        "telemetry_event_ids": state.get("telemetry_event_ids") or [],
        "created_at": state.get("created_at") or now,
        "updated_at": now,
    }


def plan_disruption(state: OrchestrationState) -> dict[str, Any]:
    """Invoke Red Agent to formulate an evidence-grounded disruption plan."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)

    iter_count = state.get("iteration_count", 0) + 1
    max_iters = state.get("max_iterations", 5)
    if iter_count > max_iters:
        return {
            "iteration_count": iter_count,
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "failure_stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "error": f"Max iteration bounds ({max_iters}) exceeded.",
            "updated_at": now,
        }

    # If LLM disabled, use deterministic allowlisted scenario
    if not state.get("use_llm", True):
        scenario = state.get("scenario_id") or "link_disruption"
        return {
            "iteration_count": iter_count,
            "red_plan": {
                "scenario_id": scenario,
                "rationale": f"Deterministic default plan for {scenario} (LLM disabled).",
                "planner_model": "deterministic",
            },
            "scenario_id": scenario,
            "stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "updated_at": now,
        }

    try:
        plan = ctx.red_agent.plan(goal=state.get("goal", "Test network resilience"))
        return {
            "iteration_count": iter_count,
            "red_plan": plan,
            "scenario_id": plan.get("scenario_id"),
            "stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "updated_at": now,
        }
    except Exception as exc:
        return {
            "iteration_count": iter_count,
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "failure_stage": OrchestrationStage.PLAN_DISRUPTION.value,
            "error": f"Red Agent planning failed: {exc}",
            "updated_at": now,
        }


def execute_disruption(state: OrchestrationState) -> dict[str, Any]:
    """Execute the allowlisted scenario against the simulated network."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)

    scenario_id = state.get("scenario_id")
    if not scenario_id and state.get("red_plan"):
        scenario_id = state["red_plan"].get("scenario_id")

    if not scenario_id:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EXECUTE_DISRUPTION.value,
            "failure_stage": OrchestrationStage.EXECUTE_DISRUPTION.value,
            "error": "No disruption scenario provided or planned.",
            "updated_at": now,
        }

    try:
        result = ctx.red_agent.execute(scenario_id=scenario_id)
        return {
            "disruption_result": result,
            "scenario_id": scenario_id,
            "stage": OrchestrationStage.EXECUTE_DISRUPTION.value,
            "updated_at": now,
        }
    except Exception as exc:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EXECUTE_DISRUPTION.value,
            "failure_stage": OrchestrationStage.EXECUTE_DISRUPTION.value,
            "error": f"Red Agent execution failed: {exc}",
            "updated_at": now,
        }


def detect_anomaly(state: OrchestrationState) -> dict[str, Any]:
    """Call Blue Sentinel to independently inspect observable simulator state."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)

    try:
        # Note: Do not pass flow_features; preserving explicit unavailable status for ML
        # per project rules (simulator does not generate 67 CICIDS features).
        report = ctx.sentinel.detect(
            flow_features=None,
            use_llm=state.get("use_llm", True),
        )
        report_dict = report.model_dump(mode="json")
        is_anomaly = report.status != DetectionStatus.HEALTHY

        return {
            "sentinel_report": report_dict,
            "detection_id": report.detection_id,
            "detection_evidence": report_dict.get("evidence"),
            "is_anomaly": is_anomaly,
            "stage": OrchestrationStage.DETECT_ANOMALY.value,
            "updated_at": now,
        }
    except Exception as exc:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.DETECT_ANOMALY.value,
            "failure_stage": OrchestrationStage.DETECT_ANOMALY.value,
            "error": f"Blue Sentinel detection failed: {exc}",
            "updated_at": now,
        }


def evaluate_detection(state: OrchestrationState) -> dict[str, Any]:
    """Evaluate Sentinel report to determine if mitigation is required."""
    now = datetime.now(timezone.utc).isoformat()
    report = state.get("sentinel_report") or {}
    det_status = report.get("status")

    if det_status == DetectionStatus.HEALTHY.value:
        return {
            "status": OrchestrationStatus.COMPLETED_HEALTHY.value,
            "stage": OrchestrationStage.EVALUATE_DETECTION.value,
            "is_anomaly": False,
            "updated_at": now,
        }
    elif det_status in (
        DetectionStatus.ANOMALY_DETECTED.value,
        DetectionStatus.INVESTIGATION_REQUIRED.value,
    ):
        return {
            "stage": OrchestrationStage.EVALUATE_DETECTION.value,
            "is_anomaly": True,
            "updated_at": now,
        }
    else:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EVALUATE_DETECTION.value,
            "failure_stage": OrchestrationStage.EVALUATE_DETECTION.value,
            "error": f"Invalid or missing Sentinel detection status: {det_status!r}",
            "updated_at": now,
        }


def recommend_recovery(state: OrchestrationState) -> dict[str, Any]:
    """Call Blue Response to formulate an evidence-grounded mitigation recommendation."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)
    sentinel_report = state.get("sentinel_report")

    if not sentinel_report:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.RECOMMEND_RECOVERY.value,
            "failure_stage": OrchestrationStage.RECOMMEND_RECOVERY.value,
            "error": "Cannot recommend recovery without Sentinel detection report.",
            "updated_at": now,
        }

    try:
        rec = ctx.blue_response.recommend(
            detection_report=sentinel_report,
            use_llm=state.get("use_llm", True),
        )
        rec_dict = rec.model_dump(mode="json")
        return {
            "recommendation": rec_dict,
            "recommendation_id": rec.recommendation_id,
            "approval_required": rec.approval_required,
            "approval_status": rec.approval_status.value,
            "stage": OrchestrationStage.RECOMMEND_RECOVERY.value,
            "updated_at": now,
        }
    except Exception as exc:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.RECOMMEND_RECOVERY.value,
            "failure_stage": OrchestrationStage.RECOMMEND_RECOVERY.value,
            "error": f"Blue Response recommendation failed: {exc}",
            "updated_at": now,
        }


def validate_recommendation(state: OrchestrationState) -> dict[str, Any]:
    """Validate proposed recommendation action and target against current simulator state."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)
    rec = state.get("recommendation") or {}

    action_type = rec.get("action_type")
    target = rec.get("target")

    if not action_type:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
            "failure_stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
            "error": "Missing action_type in recommendation.",
            "updated_at": now,
        }

    val = ctx.blue_response.validate_action(action_type, target)
    val_dict = val.model_dump(mode="json")

    if not val.valid:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
            "failure_stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
            "error": f"Recommendation validation failed: {'; '.join(val.errors)}",
            "validation_result": val_dict,
            "updated_at": now,
        }

    if action_type == RecoveryActionType.NO_ACTION.value:
        return {
            "status": OrchestrationStatus.COMPLETED_NO_ACTION.value,
            "stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
            "validation_result": val_dict,
            "updated_at": now,
        }

    return {
        "validation_result": val_dict,
        "stage": OrchestrationStage.VALIDATE_RECOMMENDATION.value,
        "updated_at": now,
    }


def request_human_approval(state: OrchestrationState) -> dict[str, Any]:
    """Human-in-the-loop approval gate.

    Pauses execution via interrupt() yielding the pending recommendation context.
    Resumes with explicit operator decision.
    CRITICAL: Does not execute state-changing actions before interrupt to prevent
    duplicate execution if node restarts.
    """
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)
    rec = state.get("recommendation") or {}
    rec_id = state.get("recommendation_id")

    # Record pause event to telemetry
    try:
        ctx.simulation.telemetry.record_event(
            event_type="orchestration_run_paused",
            message=f"Run {run_id} paused awaiting operator approval for {rec_id}.",
            severity="info",
            source="orchestrator",
            entity_id=run_id,
            details={"recommendation_id": rec_id, "action_type": rec.get("action_type")},
        )
    except Exception:
        pass

    # LangGraph Interrupt: yields payload and blocks until Command(resume=decision)
    decision_data = interrupt(
        {
            "run_id": run_id,
            "recommendation_id": rec_id,
            "action_type": rec.get("action_type"),
            "target": rec.get("target"),
            "reason": rec.get("reason"),
            "expected_effect": rec.get("expected_effect"),
            "prompt": "Operator approval required for state-changing network recovery.",
        }
    )

    # Validate the operator resume payload
    if not isinstance(decision_data, dict):
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "failure_stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "error": "Operator decision payload must be a JSON object / dict.",
            "updated_at": now,
        }

    provided_rec_id = decision_data.get("recommendation_id")
    if provided_rec_id != rec_id:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "failure_stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "error": (
                f"Recommendation ID mismatch: expected pending recommendation {rec_id!r}, "
                f"but received {provided_rec_id!r}."
            ),
            "updated_at": now,
        }

    raw_decision = str(decision_data.get("decision", "")).strip().lower()
    approver = str(decision_data.get("approver", "operator")).strip() or "operator"
    notes = str(decision_data.get("notes") or decision_data.get("reason") or "").strip()

    if raw_decision in ("approve", "approved"):
        try:
            approved_rec = ctx.blue_response.approve_recommendation(
                recommendation_id=rec_id,
                approver=approver,
                notes=notes,
            )
            return {
                "approval_status": ApprovalStatus.APPROVED.value,
                "approver": approver,
                "approval_notes": notes,
                "approval_decision": decision_data,
                "recommendation": approved_rec.model_dump(mode="json"),
                "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "updated_at": now,
            }
        except Exception as exc:
            return {
                "status": OrchestrationStatus.FAILED.value,
                "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "failure_stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "error": f"Failed to approve recommendation: {exc}",
                "updated_at": now,
            }

    elif raw_decision in ("reject", "rejected"):
        try:
            rejected_rec = ctx.blue_response.reject_recommendation(
                recommendation_id=rec_id,
                approver=approver,
                reason=notes,
            )
            return {
                "status": OrchestrationStatus.REJECTED.value,
                "approval_status": ApprovalStatus.REJECTED.value,
                "approver": approver,
                "approval_notes": notes,
                "approval_decision": decision_data,
                "recommendation": rejected_rec.model_dump(mode="json"),
                "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "updated_at": now,
            }
        except Exception as exc:
            return {
                "status": OrchestrationStatus.FAILED.value,
                "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "failure_stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
                "error": f"Failed to reject recommendation: {exc}",
                "updated_at": now,
            }

    else:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "failure_stage": OrchestrationStage.REQUEST_HUMAN_APPROVAL.value,
            "error": f"Invalid operator decision {raw_decision!r}. Allowed: 'approve', 'reject'.",
            "updated_at": now,
        }


def execute_recovery(state: OrchestrationState) -> dict[str, Any]:
    """Execute the approved mitigation via Blue Response guards."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)

    # Safety Guard: Ensure approval
    if state.get("approval_status") != ApprovalStatus.APPROVED.value:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "failure_stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "error": "Cannot execute recovery: recommendation is not approved.",
            "updated_at": now,
        }

    # Safety Guard: Ensure not previously executed in this run
    if state.get("recovery_executed", False):
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "failure_stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "error": "Recovery action has already been executed for this run.",
            "updated_at": now,
        }

    rec_id = state.get("recommendation_id")
    try:
        exec_result = ctx.blue_response.execute_approved(recommendation_id=rec_id)
        exec_dict = exec_result.model_dump(mode="json")
        ver_dict = exec_result.verification.model_dump(mode="json")

        return {
            "recovery_executed": True,
            "recovery_result": exec_dict,
            "verification_report": ver_dict,
            "stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "updated_at": now,
        }
    except Exception as exc:
        return {
            "status": OrchestrationStatus.FAILED.value,
            "stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "failure_stage": OrchestrationStage.EXECUTE_RECOVERY.value,
            "error": f"Recovery execution failed: {exc}",
            "updated_at": now,
        }


def verify_recovery(state: OrchestrationState) -> dict[str, Any]:
    """Evaluate independent post-recovery verification report."""
    now = datetime.now(timezone.utc).isoformat()
    ver = state.get("verification_report") or {}
    ver_status = ver.get("status")

    if ver_status == VerificationStatus.VERIFIED_SUCCESS.value:
        return {
            "status": OrchestrationStatus.COMPLETED.value,
            "stage": OrchestrationStage.VERIFY_RECOVERY.value,
            "updated_at": now,
        }
    elif ver_status == VerificationStatus.PARTIAL_RECOVERY.value:
        return {
            "status": OrchestrationStatus.PARTIAL_SUCCESS.value,
            "stage": OrchestrationStage.VERIFY_RECOVERY.value,
            "updated_at": now,
        }
    else:
        # Verification failed or missing: Do NOT report success
        return {
            "status": OrchestrationStatus.VERIFICATION_FAILED.value,
            "stage": OrchestrationStage.VERIFY_RECOVERY.value,
            "failure_stage": OrchestrationStage.VERIFY_RECOVERY.value,
            "error": f"Post-recovery verification failed (status: {ver_status!r}).",
            "updated_at": now,
        }


def finalize_run(state: OrchestrationState) -> dict[str, Any]:
    """Finalize run timestamps, record telemetry, and format output."""
    now = datetime.now(timezone.utc).isoformat()
    run_id = state["run_id"]
    ctx = runtime_context_manager.get_context(run_id)

    status = state.get("status", OrchestrationStatus.COMPLETED.value)
    if status == OrchestrationStatus.RUNNING.value:
        status = OrchestrationStatus.COMPLETED.value

    # Record finalization event to telemetry
    try:
        ctx.simulation.telemetry.record_event(
            event_type="orchestration_run_finalized",
            message=f"Orchestration run {run_id} finalized with status: {status}.",
            severity="info" if "failed" not in status else "warning",
            source="orchestrator",
            entity_id=run_id,
            details={
                "status": status,
                "failure_stage": state.get("failure_stage"),
                "error": state.get("error"),
            },
        )
    except Exception:
        pass

    return {
        "status": status,
        "stage": OrchestrationStage.COMPLETED.value,
        "completed_at": now,
        "updated_at": now,
    }


# -----------------------------------------------------------------------------
# Conditional Edge Routers
# -----------------------------------------------------------------------------


def route_after_initialize(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    if state.get("skip_disruption", False):
        return "detect_anomaly"
    if state.get("scenario_id"):
        return "execute_disruption"
    return "plan_disruption"


def route_after_plan(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    return "execute_disruption"


def route_after_disruption(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    return "detect_anomaly"


def route_after_detect(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    return "evaluate_detection"


def route_after_evaluate(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    if state.get("status") == OrchestrationStatus.COMPLETED_HEALTHY.value or not state.get("is_anomaly", True):
        return "finalize_run"
    return "recommend_recovery"


def route_after_recommend(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    return "validate_recommendation"


def route_after_validate(state: OrchestrationState) -> str:
    if state.get("status") in (
        OrchestrationStatus.FAILED.value,
        OrchestrationStatus.COMPLETED_NO_ACTION.value,
    ):
        return "finalize_run"
    return "request_human_approval"


def route_after_approval(state: OrchestrationState) -> str:
    if (
        state.get("approval_status") == ApprovalStatus.APPROVED.value
        and state.get("status") != OrchestrationStatus.FAILED.value
    ):
        return "execute_recovery"
    return "finalize_run"


def route_after_execute_recovery(state: OrchestrationState) -> str:
    if state.get("status") == OrchestrationStatus.FAILED.value:
        return "finalize_run"
    return "verify_recovery"


def route_after_verify(state: OrchestrationState) -> str:
    return "finalize_run"


# -----------------------------------------------------------------------------
# Graph Construction & Compilation
# -----------------------------------------------------------------------------


def build_resilience_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the NetMind network resilience LangGraph workflow."""
    builder = StateGraph(OrchestrationState)

    # 1. Add all workflow nodes
    builder.add_node("initialize_run", initialize_run)
    builder.add_node("plan_disruption", plan_disruption)
    builder.add_node("execute_disruption", execute_disruption)
    builder.add_node("detect_anomaly", detect_anomaly)
    builder.add_node("evaluate_detection", evaluate_detection)
    builder.add_node("recommend_recovery", recommend_recovery)
    builder.add_node("validate_recommendation", validate_recommendation)
    builder.add_node("request_human_approval", request_human_approval)
    builder.add_node("execute_recovery", execute_recovery)
    builder.add_node("verify_recovery", verify_recovery)
    builder.add_node("finalize_run", finalize_run)

    # 2. Add edges with conditional branching
    builder.add_edge(START, "initialize_run")

    builder.add_conditional_edges(
        "initialize_run",
        route_after_initialize,
        {
            "plan_disruption": "plan_disruption",
            "execute_disruption": "execute_disruption",
            "detect_anomaly": "detect_anomaly",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "plan_disruption",
        route_after_plan,
        {
            "execute_disruption": "execute_disruption",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "execute_disruption",
        route_after_disruption,
        {
            "detect_anomaly": "detect_anomaly",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "detect_anomaly",
        route_after_detect,
        {
            "evaluate_detection": "evaluate_detection",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "evaluate_detection",
        route_after_evaluate,
        {
            "recommend_recovery": "recommend_recovery",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "recommend_recovery",
        route_after_recommend,
        {
            "validate_recommendation": "validate_recommendation",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "validate_recommendation",
        route_after_validate,
        {
            "request_human_approval": "request_human_approval",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "request_human_approval",
        route_after_approval,
        {
            "execute_recovery": "execute_recovery",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "execute_recovery",
        route_after_execute_recovery,
        {
            "verify_recovery": "verify_recovery",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_conditional_edges(
        "verify_recovery",
        route_after_verify,
        {
            "finalize_run": "finalize_run",
        },
    )

    builder.add_edge("finalize_run", END)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=saver)


# -----------------------------------------------------------------------------
# High-Level Orchestrator Service
# -----------------------------------------------------------------------------


class NetworkOrchestrator:
    """Production service coordinating graph runs, checkpoints, and approval resumes."""

    def __init__(self, checkpointer: BaseCheckpointSaver | None = None) -> None:
        self.checkpointer = checkpointer if checkpointer is not None else MemorySaver()
        self.graph = build_resilience_graph(checkpointer=self.checkpointer)
        self._runs: dict[str, dict[str, Any]] = {}

    def start_run(
        self,
        goal: str = "Test network resilience",
        scenario_id: str | None = None,
        skip_disruption: bool = False,
        use_llm: bool = True,
        simulation: SimulationController | None = None,
        llm: Any | None = None,
        red_agent: Any | None = None,
        sentinel: Any | None = None,
        blue_response: Any | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a new resilience coordination run.

        Runs until completion or pauses at the human approval gate.
        """
        active_run_id = run_id or f"run-{uuid4().hex[:8]}"

        # Bind runtime context for in-memory simulator objects if not already registered
        if (
            red_agent is not None
            or sentinel is not None
            or blue_response is not None
            or active_run_id not in runtime_context_manager._contexts
        ):
            runtime_context_manager.register_context(
                run_id=active_run_id,
                simulation=simulation,
                llm=llm,
                red_agent=red_agent,
                sentinel=sentinel,
                blue_response=blue_response,
            )

        initial_state: OrchestrationState = {
            "run_id": active_run_id,
            "goal": goal,
            "scenario_id": scenario_id,
            "skip_disruption": skip_disruption,
            "use_llm": use_llm,
            "status": OrchestrationStatus.INITIALIZED.value,
            "stage": OrchestrationStage.INITIALIZED.value,
        }

        config = {"configurable": {"thread_id": active_run_id}}

        # Execute graph (will pause if an interrupt() occurs)
        self.graph.invoke(initial_state, config=config)

        current_state = self.get_run(active_run_id)
        self._runs[active_run_id] = current_state
        return current_state

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Inspect the current state and approval status of a run."""
        config = {"configurable": {"thread_id": run_id}}
        snapshot = self.graph.get_state(config)

        if not snapshot.values:
            if run_id in self._runs:
                return self._runs[run_id]
            raise KeyError(f"Orchestration run '{run_id}' not found.")

        state = dict(snapshot.values)

        # Check if the graph is currently interrupted / waiting for approval
        is_paused = bool(snapshot.tasks and any(t.interrupts for t in snapshot.tasks))
        if is_paused:
            state["pending_approval"] = True
            state["status"] = OrchestrationStatus.PENDING_APPROVAL.value
            state["stage"] = OrchestrationStage.REQUEST_HUMAN_APPROVAL.value
        else:
            state["pending_approval"] = False

        self._runs[run_id] = state
        return state

    def resume_run(
        self,
        run_id: str,
        decision: str,
        recommendation_id: str,
        approver: str = "operator",
        notes: str = "",
    ) -> dict[str, Any]:
        """Resume a paused run with an explicit operator approval or rejection decision."""
        config = {"configurable": {"thread_id": run_id}}
        snapshot = self.graph.get_state(config)

        if not snapshot.values:
            raise KeyError(f"Orchestration run '{run_id}' not found.")

        is_paused = bool(snapshot.tasks and any(t.interrupts for t in snapshot.tasks))
        if not is_paused:
            current_status = snapshot.values.get("status", "unknown")
            raise RuntimeError(
                f"Run '{run_id}' is not pending approval (current status: {current_status!r})."
            )

        pending_rec_id = snapshot.values.get("recommendation_id")
        if recommendation_id != pending_rec_id:
            raise ValueError(
                f"Recommendation ID mismatch: expected pending recommendation {pending_rec_id!r}, "
                f"received {recommendation_id!r}."
            )

        norm_decision = decision.strip().lower()
        if norm_decision not in ("approve", "approved", "reject", "rejected"):
            raise ValueError(
                f"Invalid decision {decision!r}. Allowed decisions: 'approve', 'reject'."
            )

        resume_payload = {
            "decision": norm_decision,
            "recommendation_id": recommendation_id,
            "approver": approver,
            "notes": notes,
        }

        # Resume the interrupted execution
        self.graph.invoke(Command(resume=resume_payload), config=config)

        current_state = self.get_run(run_id)
        self._runs[run_id] = current_state
        return current_state

    def list_runs(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        """List tracked runs, optionally filtered by status."""
        runs = [self.get_run(rid) for rid in list(self._runs.keys())]
        if status_filter:
            return [r for r in runs if r.get("status") == status_filter]
        return runs

    def get_verification(self, run_id: str) -> dict[str, Any]:
        """Retrieve the verification report for an executed run."""
        state = self.get_run(run_id)
        ver = state.get("verification_report")
        if not ver:
            status = state.get("status")
            raise KeyError(
                f"No verification report available for run '{run_id}' (status: {status!r})."
            )
        return ver
