
import pytest

from backend.network.topology import create_demo_topology
from backend.network.traffic import TrafficEngine, TrafficFlow
from backend.network.telemetry import TelemetryCollector


@pytest.fixture
def system(tmp_path):
    topology = create_demo_topology()
    traffic = TrafficEngine(topology)

    traffic.add_flow(
        TrafficFlow(
            id="flow-001",
            source="client-1",
            destination="server-1",
            packets_per_second=100,
            packet_size_bytes=1000,
        )
    )

    telemetry = TelemetryCollector(
        topology,
        traffic,
        event_log_path=tmp_path / "integration.jsonl",
    )

    return topology, traffic, telemetry


def test_flow_routing_metrics_and_event_recording(system):
    topology, traffic, telemetry = system

    summary = traffic.flow_summary("flow-001")
    event = telemetry.record_flow_state("flow-001")
    metrics = telemetry.collect_metrics()

    assert summary["reachable"] is True
    assert summary["route"] == [
        "client-1",
        "switch-1",
        "server-1",
    ]
    assert summary["path_latency_ms"] == pytest.approx(5.0)
    assert summary["offered_mbps"] == pytest.approx(0.8)

    assert event["event_type"] == "flow_active"
    assert event["entity_id"] == "flow-001"
    assert event["details"]["reachable"] is True

    assert metrics["traffic"]["total_flows"] == 1
    assert metrics["traffic"]["reachable_active_flows"] == 1
    assert metrics["traffic"]["total_offered_mbps"] == pytest.approx(0.8)
    assert metrics["traffic"]["average_path_latency_ms"] == pytest.approx(5.0)


def test_link_failure_updates_routing_and_metrics(system):
    topology, traffic, telemetry = system

    # Disable both routes from switch-1 toward server-1.
    topology.set_link_status("switch-1", "router-1", False)
    topology.set_link_status("switch-1", "server-1", False)

    summary = traffic.flow_summary("flow-001")
    event = telemetry.record_flow_state("flow-001")
    metrics = telemetry.collect_metrics()

    assert summary["reachable"] is False
    assert summary["route"] is None
    assert summary["path_latency_ms"] is None

    assert event["severity"] == "warning"
    assert event["details"]["reachable"] is False

    assert metrics["traffic"]["total_flows"] == 1
    assert metrics["traffic"]["active_flows"] == 1
    assert metrics["traffic"]["reachable_active_flows"] == 0
    assert metrics["traffic"]["total_offered_mbps"] == 0
    assert metrics["traffic"]["average_path_latency_ms"] is None


def test_disabling_flow_updates_active_metrics(system):
    topology, traffic, telemetry = system

    traffic.flows["flow-001"].active = False

    event = telemetry.record_flow_state("flow-001")
    metrics = telemetry.collect_metrics()

    assert event["event_type"] == "flow_inactive"
    assert metrics["traffic"]["total_flows"] == 1
    assert metrics["traffic"]["active_flows"] == 0
    assert metrics["traffic"]["reachable_active_flows"] == 0
    assert metrics["traffic"]["total_offered_mbps"] == 0
    assert metrics["traffic"]["average_path_latency_ms"] is None


def test_event_survives_collector_restart(system):
    topology, traffic, telemetry = system

    original = telemetry.record_flow_state("flow-001")

    recovered = TelemetryCollector(
        topology,
        traffic,
        event_log_path=telemetry.event_log_path,
    )

    events = recovered.get_events()

    assert len(events) == 1
    assert events[0]["id"] == original["id"]
    assert events[0]["entity_id"] == "flow-001"
    assert events[0]["details"]["route"] == original["details"]["route"]


def test_event_ids_continue_across_integrated_restarts(system):
    topology, traffic, telemetry = system

    first = telemetry.record_flow_state("flow-001")

    restarted = TelemetryCollector(
        topology,
        traffic,
        event_log_path=telemetry.event_log_path,
    )
    second = restarted.record_flow_state("flow-001")

    assert first["id"] == "evt-000001"
    assert second["id"] == "evt-000002"
    assert len(restarted.get_events()) == 2


def test_multiple_flows_are_reflected_in_metrics(system):
    topology, traffic, telemetry = system

    traffic.add_flow(
        TrafficFlow(
            id="flow-002",
            source="client-1",
            destination="server-2",
            packets_per_second=200,
            packet_size_bytes=1000,
        )
    )

    metrics = telemetry.collect_metrics()["traffic"]

    assert metrics["total_flows"] == 2
    assert metrics["active_flows"] == 2
    assert metrics["reachable_active_flows"] == 2
    assert metrics["total_offered_mbps"] == pytest.approx(2.4)

    # Flow 1: 5 ms; Flow 2: 6.5 ms. Average: 5.75 ms.
    assert metrics["average_path_latency_ms"] == pytest.approx(5.75)


def test_empty_traffic_system_reports_empty_metrics(tmp_path):
    topology = create_demo_topology()
    traffic = TrafficEngine(topology)

    telemetry = TelemetryCollector(
        topology,
        traffic,
        event_log_path=tmp_path / "empty.jsonl",
    )

    metrics = telemetry.collect_metrics()["traffic"]

    assert metrics["total_flows"] == 0
    assert metrics["active_flows"] == 0
    assert metrics["reachable_active_flows"] == 0
    assert metrics["total_offered_mbps"] == 0
    assert metrics["average_path_latency_ms"] is None


def test_unreachable_flow_is_recorded_without_crashing(system):
    topology, traffic, telemetry = system

    topology.set_node_status("server-1", False)

    event = telemetry.record_flow_state("flow-001")
    metrics = telemetry.collect_metrics()["traffic"]

    assert event["severity"] == "warning"
    assert event["details"]["reachable"] is False
    assert metrics["active_flows"] == 1
    assert metrics["reachable_active_flows"] == 0
    assert metrics["average_path_latency_ms"] is None


def test_recovered_event_history_preserves_order(system):
    topology, traffic, telemetry = system

    first = telemetry.record_event("simulation_started", "Started")
    second = telemetry.record_flow_state("flow-001")
    third = telemetry.record_event("simulation_stopped", "Stopped")

    recovered = TelemetryCollector(
        topology,
        traffic,
        event_log_path=telemetry.event_log_path,
    )

    events = recovered.get_events()

    assert [event["id"] for event in events] == [
        third["id"],
        second["id"],
        first["id"],
    ]
