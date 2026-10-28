"""Pydantic schemas for the NetMind Orchestration API."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class OrchestrationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(
        default="Test network resilience",
        min_length=1,
        description="High-level operational goal for the resilience workflow",
    )
    scenario_id: str | None = Field(
        default=None,
        description="Optional scenario override: 'link_disruption' or 'server_disruption'",
    )
    skip_disruption: bool = Field(
        default=False,
        description="If True, skips disruption to evaluate a healthy baseline network",
    )
    use_llm: bool = Field(
        default=True,
        description="Whether agents formulate plans and assessments using LLM",
    )


class OrchestrationResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(
        description="Operator decision: 'approve' to execute recovery, or 'reject' to abort",
    )
    recommendation_id: str = Field(
        min_length=1,
        description="Recommendation ID matching the pending approval",
    )
    approver: str = Field(
        default="operator",
        min_length=1,
        description="Name or role of the approving or rejecting operator",
    )
    notes: str = Field(
        default="",
        description="Optional approval notes or rejection rationale",
    )


class OrchestrationRunResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(description="Unique run identifier")
    status: str = Field(description="Current status (e.g. running, pending_approval, completed, failed)")
    stage: str = Field(description="Current workflow stage")
    goal: str = Field(description="Workflow goal")
    pending_approval: bool = Field(default=False, description="Whether execution is paused awaiting human approval")

    scenario_id: str | None = Field(default=None)
    red_plan: dict[str, Any] | None = Field(default=None)
    disruption_result: dict[str, Any] | None = Field(default=None)
    sentinel_report: dict[str, Any] | None = Field(default=None)
    recommendation: dict[str, Any] | None = Field(default=None)
    recommendation_id: str | None = Field(default=None)

    approval_status: str | None = Field(default=None)
    approver: str | None = Field(default=None)

    recovery_executed: bool = Field(default=False)
    recovery_result: dict[str, Any] | None = Field(default=None)
    verification_report: dict[str, Any] | None = Field(default=None)

    error: str | None = Field(default=None)
    failure_stage: str | None = Field(default=None)

    created_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)
    completed_at: str | None = Field(default=None)
