
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.schemas.events import (
    EventSeverity,
    EventSource,
    NetworkEvent,
)


@pytest.fixture
def valid_event_data():
    return {
        "id": "evt-000001",
        "timestamp": "2026-10-23T10:30:00Z",
        "event_type": "flow_active",
        "severity": "info",
        "source": "traffic_engine",
        "entity_id": "flow-001",
        "message": "Traffic flow became active",
        "details": {"packets_per_second": 100},
    }


# -------------------------------------------------------------------
# Valid events and defaults
# -------------------------------------------------------------------

def test_valid_event_is_created(valid_event_data):
    event = NetworkEvent(**valid_event_data)

    assert event.id == "evt-000001"
    assert event.event_type == "flow_active"
    assert event.severity == EventSeverity.INFO
    assert event.source == EventSource.TRAFFIC_ENGINE
    assert event.entity_id == "flow-001"
    assert event.message == "Traffic flow became active"
    assert event.details == {"packets_per_second": 100}


def test_event_default_values():
    event = NetworkEvent(
        id="evt-1",
        timestamp=datetime.now(timezone.utc),
        event_type="test",
        message="Test event",
    )

    assert event.severity == EventSeverity.INFO
    assert event.source == EventSource.SIMULATION
    assert event.entity_id is None
    assert event.details == {}


def test_details_default_is_independent():
    first = NetworkEvent(
        id="evt-1",
        timestamp=datetime.now(timezone.utc),
        event_type="test",
        message="First",
    )
    second = NetworkEvent(
        id="evt-2",
        timestamp=datetime.now(timezone.utc),
        event_type="test",
        message="Second",
    )

    first.details["changed"] = True

    assert second.details == {}


# -------------------------------------------------------------------
# Required fields
# -------------------------------------------------------------------

@pytest.mark.parametrize(
    "field",
    [
        "id",
        "timestamp",
        "event_type",
        "message",
    ],
)
def test_required_fields_cannot_be_missing(
    valid_event_data, field
):
    data = valid_event_data.copy()
    del data[field]

    with pytest.raises(ValidationError):
        NetworkEvent(**data)


# -------------------------------------------------------------------
# String validation
# -------------------------------------------------------------------

@pytest.mark.parametrize("event_id", ["", None])
def test_event_rejects_empty_or_null_id(
    valid_event_data, event_id
):
    valid_event_data["id"] = event_id

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


@pytest.mark.parametrize("event_type", ["", None])
def test_event_rejects_empty_or_null_event_type(
    valid_event_data, event_type
):
    valid_event_data["event_type"] = event_type

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


@pytest.mark.parametrize("message", ["", None])
def test_event_rejects_empty_or_null_message(
    valid_event_data, message
):
    valid_event_data["message"] = message

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


def test_event_accepts_whitespace_only_strings(valid_event_data):
    # Current schema enforces minimum length, not non-whitespace text.
    valid_event_data["id"] = " "
    valid_event_data["event_type"] = " "
    valid_event_data["message"] = " "

    event = NetworkEvent(**valid_event_data)

    assert event.id == " "


# -------------------------------------------------------------------
# Enum validation
# -------------------------------------------------------------------

@pytest.mark.parametrize("severity", list(EventSeverity))
def test_every_severity_value_is_accepted(
    valid_event_data, severity
):
    valid_event_data["severity"] = severity.value

    event = NetworkEvent(**valid_event_data)

    assert event.severity == severity


@pytest.mark.parametrize("source", list(EventSource))
def test_every_event_source_is_accepted(
    valid_event_data, source
):
    valid_event_data["source"] = source.value

    event = NetworkEvent(**valid_event_data)

    assert event.source == source


def test_invalid_severity_is_rejected(valid_event_data):
    valid_event_data["severity"] = "emergency"

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


def test_invalid_source_is_rejected(valid_event_data):
    valid_event_data["source"] = "unknown_component"

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


def test_enum_instances_are_accepted(valid_event_data):
    valid_event_data["severity"] = EventSeverity.WARNING
    valid_event_data["source"] = EventSource.API

    event = NetworkEvent(**valid_event_data)

    assert event.severity is EventSeverity.WARNING
    assert event.source is EventSource.API


# -------------------------------------------------------------------
# Timestamp validation
# -------------------------------------------------------------------

def test_timestamp_accepts_datetime_object(valid_event_data):
    timestamp = datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc)
    valid_event_data["timestamp"] = timestamp

    event = NetworkEvent(**valid_event_data)

    assert event.timestamp == timestamp


def test_timestamp_accepts_iso_8601_string(valid_event_data):
    event = NetworkEvent(**valid_event_data)

    assert event.timestamp.year == 2026
    assert event.timestamp.tzinfo is not None


def test_timestamp_rejects_invalid_string(valid_event_data):
    valid_event_data["timestamp"] = "not-a-timestamp"

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


def test_timestamp_rejects_null(valid_event_data):
    valid_event_data["timestamp"] = None

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


def test_naive_datetime_is_currently_accepted(valid_event_data):
    # The schema recommends UTC but does not enforce timezone awareness.
    timestamp = datetime(2026, 10, 23, 10, 30)
    valid_event_data["timestamp"] = timestamp

    event = NetworkEvent(**valid_event_data)

    assert event.timestamp.tzinfo is None


# -------------------------------------------------------------------
# Optional fields and structured details
# -------------------------------------------------------------------

def test_entity_id_can_be_null(valid_event_data):
    valid_event_data["entity_id"] = None

    event = NetworkEvent(**valid_event_data)

    assert event.entity_id is None


def test_entity_id_can_be_omitted(valid_event_data):
    del valid_event_data["entity_id"]

    event = NetworkEvent(**valid_event_data)

    assert event.entity_id is None


def test_details_accept_nested_json_data(valid_event_data):
    valid_event_data["details"] = {
        "flow": {"id": "flow-001", "active": True},
        "latencies": [1.2, 2.5, 3.0],
        "metadata": None,
    }

    event = NetworkEvent(**valid_event_data)

    assert event.details["flow"]["active"] is True
    assert event.details["latencies"] == [1.2, 2.5, 3.0]
    assert event.details["metadata"] is None


@pytest.mark.parametrize("details", [None, [], "text", 42])
def test_details_reject_non_dictionary_values(
    valid_event_data, details
):
    valid_event_data["details"] = details

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


# -------------------------------------------------------------------
# Reject unexpected fields
# -------------------------------------------------------------------

@pytest.mark.parametrize(
    "extra_field",
    ["unexpected", "user_id", "raw_packet"],
)
def test_extra_fields_are_rejected(
    valid_event_data, extra_field
):
    valid_event_data[extra_field] = "not allowed"

    with pytest.raises(ValidationError):
        NetworkEvent(**valid_event_data)


# -------------------------------------------------------------------
# Serialization and round-trip validation
# -------------------------------------------------------------------

def test_model_dump_returns_python_data(valid_event_data):
    event = NetworkEvent(**valid_event_data)
    data = event.model_dump()

    assert data["severity"] == EventSeverity.INFO
    assert data["source"] == EventSource.TRAFFIC_ENGINE
    assert isinstance(data["timestamp"], datetime)


def test_json_mode_dump_is_json_compatible(valid_event_data):
    event = NetworkEvent(**valid_event_data)
    data = event.model_dump(mode="json")

    assert data["severity"] == "info"
    assert data["source"] == "traffic_engine"
    assert isinstance(data["timestamp"], str)

    # The result must be serializable by the standard JSON library.
    json.dumps(data)


def test_model_dump_json_can_be_validated_again(valid_event_data):
    event = NetworkEvent(**valid_event_data)

    serialized = event.model_dump_json()
    restored = NetworkEvent.model_validate_json(serialized)

    assert restored == event


def test_serialization_preserves_details(valid_event_data):
    valid_event_data["details"] = {
        "route": ["client-1", "router-1", "server-1"],
        "latency_ms": 6.0,
    }

    event = NetworkEvent(**valid_event_data)
    restored = NetworkEvent.model_validate_json(
        event.model_dump_json()
    )

    assert restored.details == event.details


def test_event_schema_does_not_modify_input(valid_event_data):
    original = valid_event_data.copy()

    NetworkEvent(**valid_event_data)

    assert valid_event_data == original
