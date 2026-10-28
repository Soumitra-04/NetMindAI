"""FastAPI routes for NetMind network events."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query

import backend.api.simulation as sim_mod
from backend.services.event_service import EventService

router = APIRouter()

# Dynamically access the active simulation's telemetry (including after resets).
event_service = EventService(lambda: sim_mod.simulation.telemetry)


@router.get("/", response_model=list[dict[str, Any]])
def get_events(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum events to return"),
    severity: str | None = Query(default=None, description="Filter by event severity"),
    event_type: str | None = Query(default=None, description="Filter by event type"),
):
    """Retrieve recent simulation events with optional filtering."""
    try:
        return event_service.get_events(
            limit=limit,
            severity=severity,
            event_type=event_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
