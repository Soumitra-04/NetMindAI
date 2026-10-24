
"""Pydantic schemas for NetMind network and security events."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventSeverity(str, Enum):
    """Severity of an event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventSource(str, Enum):
    """Component that produced an event."""

    SIMULATION = "simulation"
    TOPOLOGY = "topology"
    TRAFFIC_ENGINE = "traffic_engine"
    TELEMETRY = "telemetry"
    RED_AGENT = "red_agent"
    BLUE_SENTINEL = "blue_sentinel"
    BLUE_RESPONSE = "blue_response"
    API = "api"


class NetworkEvent(BaseModel):
    """Standard structure for a NetMind event."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Unique event identifier")
    timestamp: datetime = Field(description="Event time, preferably UTC")
    event_type: str = Field(
        min_length=1,
        description="Machine-readable event category, e.g. flow_active",
    )
    severity: EventSeverity = Field(default=EventSeverity.INFO)
    source: EventSource = Field(default=EventSource.SIMULATION)
    entity_id: str | None = Field(
        default=None,
        description="Related node, link, flow, experiment, or alert ID",
    )
    message: str = Field(
        min_length=1,
        description="Human-readable summary of the event",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured event-specific data",
    )
