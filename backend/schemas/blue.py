"""Pydantic schemas for the Blue Sentinel and Blue Response agents."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DetectionStatus(str, Enum):
    HEALTHY = "healthy"
    ANOMALY_DETECTED = "anomaly_detected"
    INVESTIGATION_REQUIRED = "investigation_required"


class RecoveryActionType(str, Enum):
    RESTORE_LINK = "restore_link"
    RESTORE_NODE = "restore_node"
    NO_ACTION = "no_action"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class VerificationStatus(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    PARTIAL_RECOVERY = "partial_recovery"
    VERIFICATION_FAILED = "verification_failed"


class ModelInferenceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Status of ML inference: 'unavailable', 'completed', or 'error'")
    reason: str | None = Field(default=None, description="Explanation when inference is unavailable or failed")
    result: dict[str, Any] | None = Field(default=None, description="Prediction result when inference succeeds")


class SentinelEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inactive_nodes: list[dict[str, Any]] = Field(default_factory=list)
    inactive_links: list[dict[str, Any]] = Field(default_factory=list)
    unreachable_flows: list[dict[str, Any]] = Field(default_factory=list)
    contextual_events: list[dict[str, Any]] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)


class SentinelReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detection_id: str = Field(min_length=1, description="Unique detection identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the detection",
    )
    status: DetectionStatus = Field(description="Overall network health / anomaly status")
    findings: list[str] = Field(default_factory=list, description="Human-readable summary of detected conditions")
    affected_nodes: list[str] = Field(default_factory=list, description="Node IDs identified as disrupted")
    affected_links: list[str] = Field(default_factory=list, description="Links identified as disrupted (e.g. 'router-1<->server-1')")
    affected_flows: list[str] = Field(default_factory=list, description="Traffic flow IDs that have become unreachable")
    evidence: SentinelEvidence = Field(default_factory=SentinelEvidence, description="Independently observed state and telemetry")
    severity: str = Field(default="info", description="Severity: 'info', 'warning', or 'critical'")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Detection confidence score")
    recommended_action: str = Field(min_length=1, description="Recommended remediation summary")
    model_inference: ModelInferenceStatus = Field(description="Random forest model inference status and result")
    errors_or_limitations: list[str] = Field(default_factory=list, description="Errors or limitations during observation")


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(description="Whether the action is valid and applicable")
    errors: list[str] = Field(default_factory=list, description="Validation error messages if invalid")


class RecoveryRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(min_length=1, description="Unique recommendation ID")
    detection_id: str = Field(min_length=1, description="Reference to Sentinel detection")
    action_type: RecoveryActionType = Field(description="Type of action: restore_link, restore_node, or no_action")
    target: str | None = Field(default=None, description="Target entity ID (e.g. 'router-1<->server-1' or 'server-1')")
    reason: str = Field(min_length=1, description="Evidence-grounded rationale for this recovery recommendation")
    expected_effect: str = Field(min_length=1, description="Expected operational effect of the recovery")
    preconditions: list[str] = Field(default_factory=list, description="Preconditions that must hold for execution")
    approval_required: bool = Field(default=True, description="Whether explicit operator approval is required")
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Current approval status")
    validation_result: ValidationResult = Field(description="Result of validating action against simulator state")
    created_at: datetime = Field(description="Timestamp when recommendation was formulated")
    approver: str | None = Field(default=None, description="Operator identity who approved or rejected")
    approval_notes: str | None = Field(default=None, description="Optional operator notes")


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver: str = Field(default="operator", min_length=1, description="Name or role of approver")
    notes: str = Field(default="", description="Optional approval notes")


class RejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver: str = Field(default="operator", min_length=1, description="Name or role of rejecter")
    reason: str = Field(default="", description="Reason for rejecting the recommendation")


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus = Field(description="Verification result: verified_success, partial_recovery, or verification_failed")
    target_active: bool = Field(description="Whether the target node or link is currently active")
    route_after: list[str] | None = Field(default=None, description="Shortest path route verified after recovery")
    reachable_flows: int = Field(ge=0, description="Number of currently reachable active flows")
    details: dict[str, Any] = Field(default_factory=dict, description="Detailed verification observations")


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(description="ID of the executed recommendation")
    action_type: RecoveryActionType = Field(description="Action executed")
    target: str | None = Field(default=None, description="Target entity")
    execution_status: str = Field(description="Execution result: 'success' or 'failed'")
    verification: VerificationReport = Field(description="Independent post-recovery verification report")
    timestamp: datetime = Field(description="Timestamp of execution")
