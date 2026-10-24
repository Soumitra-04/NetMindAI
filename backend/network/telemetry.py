
"""Telemetry collection for the NetMind network simulator."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any

from backend.network.topology import NetworkTopology
from backend.network.traffic import TrafficEngine
from backend.schemas.events import EventSeverity, EventSource, NetworkEvent

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """Collect network metrics and validated, persistent events."""

    def __init__(
        self,
        topology: NetworkTopology,
        traffic_engine: TrafficEngine,
        max_events: int = 1000,
        event_log_path: str | Path = "data/events.jsonl",
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1.")

        self.topology = topology
        self.traffic_engine = traffic_engine
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)

        self.event_log_path = Path(event_log_path)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Restore persisted events and continue the event ID sequence.
        next_event_number = self._load_existing_events()
        self._event_counter = count(next_event_number)

        logger.info(
            "Telemetry collector initialized. Recovered %d recent events.",
            len(self.events),
        )

    def _load_existing_events(self) -> int:
        """Load valid events and return the next numeric event ID."""

        if not self.event_log_path.exists():
            return 1

        highest_event_number = 0

        with self.event_log_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    event = NetworkEvent.model_validate_json(line)
                    event_data = event.model_dump(mode="json")
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid event at %s:%d: %s",
                        self.event_log_path,
                        line_number,
                        exc,
                    )
                    continue

                # The deque automatically retains only the newest max_events.
                self.events.append(event_data)

                event_id = event_data["id"]
                prefix = "evt-"

                if event_id.startswith(prefix):
                    suffix = event_id[len(prefix):]
                    if suffix.isdigit():
                        highest_event_number = max(
                            highest_event_number,
                            int(suffix),
                        )

        return highest_event_number + 1

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
        """Validate, persist, store, and log a structured event."""

        event = NetworkEvent(
            id=f"evt-{next(self._event_counter):06d}",
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=EventSeverity(severity),
            source=EventSource(source),
            entity_id=entity_id,
            message=message,
            details=details or {},
        )

        event_data = event.model_dump(mode="json")

        # Persist before updating in-memory history.
        with self.event_log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event_data, ensure_ascii=False) + "\n")

        self.events.append(event_data)

        log_level = getattr(logging, event.severity.value.upper())
        logger.log(
            log_level,
            "Network event %s: %s",
            event.event_type,
            event.message,
            extra={
                "event_id": event.id,
                "event_type": event.event_type,
            },
        )

        return event_data

    def get_events(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the newest matching in-memory events first."""

        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        if severity is not None:
            EventSeverity(severity)

        return [
            event
            for event in reversed(self.events)
            if (severity is None or event["severity"] == severity)
            and (event_type is None or event["event_type"] == event_type)
        ][:limit]

    def collect_metrics(self) -> dict[str, Any]:
        """Collect the measurements currently supported by the simulator."""

        flows = self.traffic_engine.all_flows()

        reachable_active_flows = [
            flow for flow in flows
            if flow["reachable"] and flow["active"]
        ]

        total_offered_mbps = sum(
            flow["offered_mbps"] for flow in reachable_active_flows
        )

        latencies = [
            flow["path_latency_ms"]
            for flow in reachable_active_flows
            if flow["path_latency_ms"] is not None
        ]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topology": {
                "total_nodes": len(self.topology.nodes),
                "active_nodes": sum(
                    node.active for node in self.topology.nodes.values()
                ),
                "total_links": len(self.topology.links),
                "active_links": sum(
                    link.active for link in self.topology.links
                ),
            },
            "traffic": {
                "total_flows": len(flows),
                "active_flows": sum(
                    flow["active"] for flow in flows
                ),
                "reachable_active_flows": len(reachable_active_flows),
                "total_offered_mbps": round(total_offered_mbps, 6),
                "average_path_latency_ms": (
                    round(sum(latencies) / len(latencies), 3)
                    if latencies
                    else None
                ),
            },
            "limitations": [
                "Traffic rates represent offered load, not delivered throughput.",
                "Packet loss and link utilization are not yet simulated.",
            ],
        }

    def record_flow_state(self, flow_id: str) -> dict[str, Any]:
        """Record the current state of a registered traffic flow."""

        summary = self.traffic_engine.flow_summary(flow_id)

        event_type = (
            "flow_active" if summary["active"] else "flow_inactive"
        )
        severity = "info" if summary["reachable"] else "warning"

        return self.record_event(
            event_type=event_type,
            message=(
                f"Flow {flow_id}: "
                f"{summary['source']} -> {summary['destination']}"
            ),
            severity=severity,
            source="traffic_engine",
            entity_id=flow_id,
            details=summary,
        )
