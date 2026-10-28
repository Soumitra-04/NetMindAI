"""Event service for querying and recording NetMind network and security events."""

from __future__ import annotations

from typing import Any, Callable

from backend.network.telemetry import TelemetryCollector


class EventService:
    """Service layer interface for network telemetry events."""

    def __init__(
        self,
        telemetry: TelemetryCollector | Callable[[], TelemetryCollector],
    ) -> None:
        self._telemetry = telemetry

    @property
    def telemetry(self) -> TelemetryCollector:
        """Resolve telemetry collector dynamically if passed as a callable."""
        if callable(self._telemetry):
            return self._telemetry()
        return self._telemetry

    def get_events(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve recent structured events matching query filters."""
        return self.telemetry.get_events(
            limit=limit,
            severity=severity,
            event_type=event_type,
        )

    def record_event(
        self,
        event_type: str,
        message: str,
        *,
        severity: str = "info",
        source: str = "simulation",
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record and persist a structured network event."""
        return self.telemetry.record_event(
            event_type=event_type,
            message=message,
            severity=severity,
            source=source,
            entity_id=entity_id,
            details=details,
        )
