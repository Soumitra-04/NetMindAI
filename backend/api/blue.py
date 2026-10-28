"""FastAPI routes for the Blue Sentinel and Blue Response agents."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, status

import backend.api.simulation as sim_mod
from backend.agents.blue_response import BlueResponse
from backend.agents.blue_sentinel import BlueSentinel
from backend.schemas.blue import (
    ApprovalRequest,
    ExecutionResult,
    RecoveryRecommendation,
    RejectionRequest,
    SentinelReport,
    VerificationReport,
)

router = APIRouter()

# Dynamically access the active simulation (including across simulation resets)
sentinel = BlueSentinel(lambda: sim_mod.simulation)
response_agent = BlueResponse(lambda: sim_mod.simulation)


@router.post("/sentinel/detect", response_model=SentinelReport)
def run_sentinel_detection(
    use_llm: bool = Query(default=True, description="Whether to include LLM evidence interpretation"),
    flow_features: dict[str, Any] | list[dict[str, Any]] | None = None,
):
    """Run independent detection across topology, traffic, telemetry, and optional ML."""
    try:
        return sentinel.detect(flow_features=flow_features, use_llm=use_llm)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection failed: {exc}",
        ) from exc


@router.post("/response/recommend", response_model=RecoveryRecommendation)
def request_recovery_recommendation(
    use_llm: bool = Query(default=True, description="Whether to formulate recommendation with LLM"),
    detection_report: SentinelReport | None = None,
):
    """Formulate an evidence-grounded recovery recommendation gated behind approval."""
    try:
        report = detection_report or sentinel.detect(use_llm=use_llm)
        return response_agent.recommend(report, use_llm=use_llm)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation failed: {exc}",
        ) from exc


@router.get("/response/recommendations", response_model=list[RecoveryRecommendation])
def list_recommendations(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by approval status"),
):
    """List all formulated recovery recommendations."""
    return response_agent.list_recommendations(status=status_filter)


@router.get("/response/recommendations/{recommendation_id}", response_model=RecoveryRecommendation)
def get_recommendation(recommendation_id: str):
    """Retrieve a specific recommendation by its identifier."""
    try:
        return response_agent.get_recommendation(recommendation_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/response/recommendations/{recommendation_id}/approve", response_model=RecoveryRecommendation)
def approve_recommendation(
    recommendation_id: str,
    request: ApprovalRequest = ApprovalRequest(),
):
    """Explicitly approve a pending recovery recommendation."""
    try:
        return response_agent.approve_recommendation(
            recommendation_id=recommendation_id,
            approver=request.approver,
            notes=request.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/response/recommendations/{recommendation_id}/reject", response_model=RecoveryRecommendation)
def reject_recommendation(
    recommendation_id: str,
    request: RejectionRequest = RejectionRequest(),
):
    """Explicitly reject a pending recovery recommendation."""
    try:
        return response_agent.reject_recommendation(
            recommendation_id=recommendation_id,
            approver=request.approver,
            reason=request.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/response/recommendations/{recommendation_id}/execute", response_model=ExecutionResult)
def execute_approved_recommendation(recommendation_id: str):
    """Execute an approved recovery action and verify the operational outcome."""
    try:
        return response_agent.execute_approved(recommendation_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/response/recommendations/{recommendation_id}/verification", response_model=VerificationReport)
def get_recommendation_verification(recommendation_id: str):
    """Inspect the post-recovery verification report for an executed action."""
    try:
        rec = response_agent.get_recommendation(recommendation_id)
        if rec.approval_status.value != "executed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recommendation '{recommendation_id}' has not been executed yet (status: {rec.approval_status.value}).",
            )
        # Search telemetry for the verification event
        events = sim_mod.simulation.telemetry.get_events(
            event_type="blue_recovery_verified",
            limit=20,
        )
        for event in events:
            if event.get("entity_id") == recommendation_id:
                return VerificationReport.model_validate(event["details"])

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verification report found for recommendation '{recommendation_id}'.",
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
