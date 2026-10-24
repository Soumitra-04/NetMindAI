
import json
import logging

import pytest

from backend.network.topology import create_demo_topology
from backend.network.traffic import TrafficEngine, TrafficFlow
from backend.network.telemetry import TelemetryCollector


@pytest.fixture
def network():
    """Create an isolated demo network for each test."""
    topology = create_demo_topology()
    traffic = TrafficEngine(topology)
    traffic.add_flow(
        TrafficFlow(
            "flow-001",
            "client-1",
            "server-1",
            packets_per_second=100,
            packet_size_bytes=1000,
        )
    )
    return topology, traffic


@pytest.fixture
def collector(network, tmp_path):
    """Create a collector with a temporary event log."""
    topology, traffic = network
    return TelemetryCollector(
        topology,
        traffic,
        max_events=1000,
        event_log_path=tmp_path / "events.jsonl",
    )


def test_record_event_returns_valid_structured_event(collector):
    event = collector.record_event(
        event_type="test_event",
        message="Telemetry test",
        source="simulation",
        severity="info",
        details={"test": True},
    )

    assert event["id"] == "evt-000001"
    assert event["event_type"] == "test_event"
    assert event["message"] == "Telemetry test"
    assert event["source"] == "simulation"
    assert event["severity"] == "info"
    assert event["details"] == {"test": True}
    assert event["timestamp"]


def test_event_is_persisted_as_jsonl(collector):
    event = collector.record_event(
        "test_event",
        "Persist this event",
    )

    lines = collector.event_log_path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1
    assert json.loads(lines[0]) == event


def test_multiple_events_receive_unique_sequential_ids(collector):
    first = collector.record_event("test", "First")
    second = collector.record_event("test", "Second")
    third = collector.record_event("test", "Third")

    assert [
        first["id"],
        second["id"],
        third["id"],
    ] == [
        "evt-000001",
        "evt-000002",
        "evt-000003",
    ]


def test_get_events_returns_newest_first(collector):
    collector.record_event("first", "First")
    collector.record_event("second", "Second")
    collector.record_event("third", "Third")

    events = collector.get_events()

    assert [event["event_type"] for event in events] == [
        "third",
        "second",
        "first",
    ]


def test_get_events_respects_limit(collector):
    for index in range(5):
        collector.record_event("test", f"Event {index}")

    assert len(collector.get_events(limit=2)) == 2


def test_get_events_filters_by_severity(collector):
    collector.record_event("test", "Info event", severity="info")
    collector.record_event("test", "Warning event", severity="warning")
    collector.record_event("test", "Error event", severity="error")

    events = collector.get_events(severity="warning")

    assert len(events) == 1
    assert events[0]["message"] == "Warning event"


def test_get_events_filters_by_event_type(collector):
    collector.record_event("flow_active", "Flow active")
    collector.record_event("node_down", "Node down")
    collector.record_event("flow_active", "Another flow active")

    events = collector.get_events(event_type="flow_active")

    assert len(events) == 2
    assert all(
        event["event_type"] == "flow_active"
        for event in events
    )


def test_get_events_combines_filters(collector):
    collector.record_event(
        "network_issue",
        "Info issue",
        severity="info",
    )
    collector.record_event(
        "network_issue",
        "Warning issue",
        severity="warning",
    )
    collector.record_event(
        "other_event",
        "Another warning",
        severity="warning",
    )

    events = collector.get_events(
        severity="warning",
        event_type="network_issue",
    )

    assert len(events) == 1
    assert events[0]["message"] == "Warning issue"


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_get_events_rejects_nonpositive_limits(collector, limit):
    with pytest.raises(ValueError):
        collector.get_events(limit=limit)


def test_get_events_rejects_invalid_severity(collector):
    with pytest.raises(ValueError):
        collector.get_events(severity="emergency")


def test_record_event_rejects_invalid_severity(collector):
    with pytest.raises(ValueError):
        collector.record_event(
            "test",
            "Invalid severity",
            severity="emergency",
        )


def test_record_event_rejects_invalid_source(collector):
    with pytest.raises(ValueError):
        collector.record_event(
            "test",
            "Invalid source",
            source="unknown_component",
        )


def test_memory_history_is_bounded(network, tmp_path):
    topology, traffic = network
    instance = TelemetryCollector(
        topology,
        traffic,
        max_events=3,
        event_log_path=tmp_path / "bounded.jsonl",
    )

    for index in range(5):
        instance.record_event("test", f"Event {index}")

    assert len(instance.events) == 3
    assert [
        event["message"] for event in instance.get_events()
    ] == ["Event 4", "Event 3", "Event 2"]

    # The persistent log should still contain every event.
    lines = instance.event_log_path.read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(lines) == 5


@pytest.mark.parametrize("max_events", [0, -1])
def test_collector_rejects_invalid_memory_limit(
    network, tmp_path, max_events
):
    topology, traffic = network

    with pytest.raises(ValueError):
        TelemetryCollector(
            topology,
            traffic,
            max_events=max_events,
            event_log_path=tmp_path / "invalid.jsonl",
        )



def test_collector_starts_with_empty_history(network, tmp_path):
    topology, traffic = network
    log_path = tmp_path / "new.jsonl"

    instance = TelemetryCollector(
        topology,
        traffic,
        event_log_path=log_path,
    )

    assert instance.get_events() == []
    assert not log_path.exists()

    # The log file should be created when the first event is recorded.
    instance.record_event("test", "First event")

    assert log_path.exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_collector_recovers_events_after_restart(network, tmp_path):
    topology, traffic = network
    path = tmp_path / "restart.jsonl"

    first_collector = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    first = first_collector.record_event("test", "Before restart")

    second_collector = TelemetryCollector(
        topology, traffic, event_log_path=path
    )

    assert len(second_collector.get_events()) == 1
    assert second_collector.get_events()[0]["id"] == first["id"]


def test_event_ids_continue_after_restart(network, tmp_path):
    topology, traffic = network
    path = tmp_path / "ids.jsonl"

    first_collector = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    first = first_collector.record_event("test", "First")

    second_collector = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    second = second_collector.record_event("test", "Second")

    assert first["id"] == "evt-000001"
    assert second["id"] == "evt-000002"


def test_malformed_json_lines_are_skipped(
    network, tmp_path, caplog
):
    topology, traffic = network
    path = tmp_path / "malformed.jsonl"

    initial = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    valid = initial.record_event("test", "Valid event")

    with path.open("a", encoding="utf-8") as file:
        file.write("{broken json}\n")
        file.write("not-json\n")
        file.write("\n")

    with caplog.at_level(logging.WARNING):
        recovered = TelemetryCollector(
            topology, traffic, event_log_path=path
        )

    assert len(recovered.events) == 1
    assert recovered.events[0]["id"] == valid["id"]
    assert "Skipping invalid event" in caplog.text


def test_valid_events_survive_between_malformed_lines(
    network, tmp_path
):
    topology, traffic = network
    path = tmp_path / "mixed.jsonl"

    initial = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    first = initial.record_event("test", "First valid event")

    with path.open("a", encoding="utf-8") as file:
        file.write("invalid line\n")

    initial.record_event("test", "Second valid event")

    recovered = TelemetryCollector(
        topology, traffic, event_log_path=path
    )

    ids = {event["id"] for event in recovered.events}

    assert ids == {first["id"], "evt-000002"}


def test_corrupt_lines_do_not_reset_event_counter(
    network, tmp_path
):
    topology, traffic = network
    path = tmp_path / "counter.jsonl"

    initial = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    initial.record_event("test", "First")

    with path.open("a", encoding="utf-8") as file:
        file.write("corrupt data\n")

    recovered = TelemetryCollector(
        topology, traffic, event_log_path=path
    )
    next_event = recovered.record_event("test", "After recovery")

    assert next_event["id"] == "evt-000002"


def test_collector_recovers_only_latest_events_in_memory(
    network, tmp_path
):
    topology, traffic = network
    path = tmp_path / "bounded-recovery.jsonl"

    original = TelemetryCollector(
        topology,
        traffic,
        max_events=5,
        event_log_path=path,
    )

    for index in range(7):
        original.record_event("test", f"Event {index}")

    recovered = TelemetryCollector(
        topology,
        traffic,
        max_events=3,
        event_log_path=path,
    )

    assert len(recovered.events) == 3
    assert [
        event["message"] for event in recovered.get_events()
    ] == ["Event 6", "Event 5", "Event 4"]

    # ID recovery must inspect the whole valid file, not just the deque.
    next_event = recovered.record_event("test", "Event 7")
    assert next_event["id"] == "evt-000008"


def test_collect_metrics_reports_topology_and_traffic(
    collector,
):
    metrics = collector.collect_metrics()

    assert metrics["topology"]["total_nodes"] == 6
    assert metrics["topology"]["total_links"] == 7

    traffic = metrics["traffic"]
    assert traffic["total_flows"] == 1
    assert traffic["active_flows"] == 1
    assert traffic["reachable_active_flows"] == 1
    assert traffic["total_offered_mbps"] == pytest.approx(0.8)
    assert traffic["average_path_latency_ms"] == pytest.approx(5.0)

    assert metrics["timestamp"]
    assert metrics["limitations"]


def test_collect_metrics_handles_no_flows(network, tmp_path):
    topology, _ = network
    traffic = TrafficEngine(topology)

    instance = TelemetryCollector(
        topology,
        traffic,
        event_log_path=tmp_path / "no-flows.jsonl",
    )

    metrics = instance.collect_metrics()

    assert metrics["traffic"]["total_flows"] == 0
    assert metrics["traffic"]["active_flows"] == 0
    assert metrics["traffic"]["total_offered_mbps"] == 0
    assert metrics["traffic"]["average_path_latency_ms"] is None


def test_record_flow_state_records_flow_details(collector):
    event = collector.record_flow_state("flow-001")

    assert event["event_type"] == "flow_active"
    assert event["source"] == "traffic_engine"
    assert event["entity_id"] == "flow-001"
    assert event["details"]["reachable"] is True


def test_record_flow_state_rejects_unknown_flow(collector):
    with pytest.raises((KeyError, ValueError)):
        collector.record_flow_state("missing-flow")
