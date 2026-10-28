"""Typed state definitions for the NetMind LangGraph orchestration layer."""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class OrchestrationStage(str, Enum):
    """Execution stages of the network resilience graph."""

    INITIALIZED = "initialized"
    PLAN_DISRUPTION = "plan_disruption"
    EXECUTE_DISRUPTION = "execute_disruption"
    DETECT_ANOMALY = "detect_anomaly"
    EVALUATE_DETECTION = "evaluate_detection"
    RECOMMEND_RECOVERY = "recommend_recovery"
    VALIDATE_RECOMMENDATION = "validate_recommendation"
    REQUEST_HUMAN_APPROVAL = "request_human_approval"
    EXECUTE_RECOVERY = "execute_recovery"
    VERIFY_RECOVERY = "verify_recovery"
    FINALIZE_RUN = "finalize_run"
    COMPLETED = "completed"


class OrchestrationStatus(str, Enum):
    """Lifecycle and terminal statuses for an orchestration run."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    COMPLETED_HEALTHY = "completed_healthy"
    COMPLETED_NO_ACTION = "completed_no_action"
    PARTIAL_SUCCESS = "partial_success"
    VERIFICATION_FAILED = "verification_failed"
    FAILED = "failed"


class OrchestrationState(TypedDict, total=False):
    """Checkpointable typed state for the resilience coordination graph.

    Contains exclusively JSON/msgpack-serializable primitives and containers.
    In-memory simulator and agent objects are decoupled into runtime context.
    """

    # Identifiers & status
    run_id: str
    status: str
    stage: str

    # Context & config
    goal: str
    scenario_id: str | None
    skip_disruption: bool
    use_llm: bool
    simulation_id: str | None
    context_data: dict[str, Any]

    # Iteration bounds
    iteration_count: int
    max_iterations: int

    # Red Agent
    red_plan: dict[str, Any] | None
    disruption_result: dict[str, Any] | None

    # Blue Sentinel
    sentinel_report: dict[str, Any] | None
    detection_evidence: dict[str, Any] | None
    detection_id: str | None
    is_anomaly: bool

    # Blue Response Recommendation
    recommendation: dict[str, Any] | None
    recommendation_id: str | None
    validation_result: dict[str, Any] | None

    # Human-in-the-loop Approval Gate
    approval_required: bool
    approval_status: str | None
    approver: str | None
    approval_notes: str | None
    approval_decision: dict[str, Any] | None

    # Recovery Execution & Verification
    recovery_executed: bool
    recovery_result: dict[str, Any] | None
    verification_report: dict[str, Any] | None

    # Telemetry and simulator events references
    telemetry_event_ids: list[str]

    # Error details & failure stage
    error: str | None
    failure_stage: str | None

    # Timestamps
    created_at: str
    updated_at: str
    completed_at: str | None
