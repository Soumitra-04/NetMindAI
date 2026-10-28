"""FastAPI routes for the NetMind LangGraph Orchestration Layer."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, status

from backend.orchestration.graph import NetworkOrchestrator
from backend.schemas.orchestration import (
    OrchestrationResumeRequest,
    OrchestrationRunResponse,
    OrchestrationStartRequest,
)

router = APIRouter()

# Global orchestrator instance for local deployment
orchestrator = NetworkOrchestrator()


@router.post("/runs", response_model=OrchestrationRunResponse)
@router.post("/runs/", response_model=OrchestrationRunResponse, include_in_schema=False)
def start_orchestration_run(
    request: OrchestrationStartRequest = OrchestrationStartRequest(),
):
    """Start an orchestration run coordinating Red disruption, Sentinel detection, and Blue mitigation."""
    try:
        run_data = orchestrator.start_run(
            goal=request.goal,
            scenario_id=request.scenario_id,
            skip_disruption=request.skip_disruption,
            use_llm=request.use_llm,
        )
        return OrchestrationRunResponse.model_validate(run_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start orchestration run: {exc}",
        ) from exc


@router.get("/runs", response_model=list[OrchestrationRunResponse])
@router.get("/runs/", response_model=list[OrchestrationRunResponse], include_in_schema=False)
def list_orchestration_runs(
    status_filter: str | None = Query(default=None, alias="status", description="Filter runs by status"),
):
    """List all tracked orchestration runs."""
    runs = orchestrator.list_runs(status_filter=status_filter)
    return [OrchestrationRunResponse.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=OrchestrationRunResponse)
def get_orchestration_run(run_id: str):
    """Retrieve the current state, progress, and approval status of a run."""
    try:
        run_data = orchestrator.get_run(run_id)
        return OrchestrationRunResponse.model_validate(run_data)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/runs/{run_id}/resume", response_model=OrchestrationRunResponse)
def resume_orchestration_run(
    run_id: str,
    request: OrchestrationResumeRequest,
):
    """Resume a paused orchestration run with an explicit operator approve or reject decision."""
    try:
        run_data = orchestrator.resume_run(
            run_id=run_id,
            decision=request.decision,
            recommendation_id=request.recommendation_id,
            approver=request.approver,
            notes=request.notes,
        )
        return OrchestrationRunResponse.model_validate(run_data)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resuming run {run_id}: {exc}",
        ) from exc


@router.get("/runs/{run_id}/verification", response_model=dict[str, Any])
def get_run_verification_report(run_id: str):
    """Inspect the post-recovery verification report for an executed orchestration run."""
    try:
        return orchestrator.get_verification(run_id)
    except KeyError as exc:
        # Check if the run itself exists
        try:
            orchestrator.get_run(run_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Orchestration run '{run_id}' not found.",
            ) from exc
