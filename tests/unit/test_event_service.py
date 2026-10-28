"""Unit tests for EventService."""

import pytest

from backend.network.simulation import SimulationController
from backend.services.event_service import EventService


@pytest.fixture
def sim_and_service(tmp_path):
    sim = SimulationController.create_demo()
    sim.telemetry.event_log_path = tmp_path / "events.jsonl"
    sim.telemetry.events.clear()
    service = EventService(sim.telemetry)
    return sim, service


def test_event_service_records_and_retrieves_event(sim_and_service):
    sim, service = sim_and_service

    recorded = service.record_event(
        event_type="test_event",
        message="A test message",
        severity="info",
        source="simulation",
        details={"key": "val"},
    )

    assert recorded["event_type"] == "test_event"
    assert recorded["message"] == "A test message"

    events = service.get_events(event_type="test_event")
    assert len(events) == 1
    assert events[0]["id"] == recorded["id"]


def test_event_service_filters_by_severity(sim_and_service):
    sim, service = sim_and_service

    service.record_event(event_type="info_ev", message="Info", severity="info")
    service.record_event(event_type="warn_ev", message="Warning", severity="warning")

    info_events = service.get_events(severity="info")
    assert len(info_events) == 1
    assert info_events[0]["event_type"] == "info_ev"

    warn_events = service.get_events(severity="warning")
    assert len(warn_events) == 1
    assert warn_events[0]["event_type"] == "warn_ev"


def test_event_service_dynamic_callable_resolution(tmp_path):
    sim = SimulationController.create_demo()
    sim.telemetry.event_log_path = tmp_path / "events1.jsonl"
    sim.telemetry.events.clear()

    holder = {"sim": sim}
    service = EventService(lambda: holder["sim"].telemetry)

    service.record_event(event_type="first_sim", message="First")
    assert len(service.get_events()) == 1

    # Reset/replace simulation
    sim2 = SimulationController.create_demo()
    sim2.telemetry.event_log_path = tmp_path / "events2.jsonl"
    sim2.telemetry.events.clear()
    holder["sim"] = sim2

    service.record_event(event_type="second_sim", message="Second")
    events = service.get_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "second_sim"
