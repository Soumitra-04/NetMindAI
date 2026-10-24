
import pytest

from backend.network.simulation import SimulationController


@pytest.fixture
def simulation():
    return SimulationController.create_demo()


def test_demo_simulation_initializes(simulation):
    assert simulation.step_number == 0
    assert len(simulation.topology.nodes) == 6
    assert len(simulation.traffic_engine.all_flows()) == 2


def test_step_increments_counter(simulation):
    first = simulation.step()
    second = simulation.step()

    assert first["step_number"] == 1
    assert second["step_number"] == 2


def test_snapshot_contains_required_sections(simulation):
    snapshot = simulation.snapshot()

    assert "step_number" in snapshot
    assert "topology" in snapshot
    assert "flows" in snapshot
    assert "metrics" in snapshot


def test_snapshot_reflects_node_status_changes(simulation):
    simulation.topology.set_node_status("server-1", active=False)

    snapshot = simulation.snapshot()
    nodes = snapshot["topology"]["nodes"]

    server = next(node for node in nodes if node["id"] == "server-1")
    assert server["active"] is False


def test_step_records_flow_events(simulation):
    previous_events = simulation.telemetry.get_events(limit=2)
    previous_ids = {event["id"] for event in previous_events}

    simulation.step()

    latest_events = simulation.telemetry.get_events(limit=2)

    assert len(latest_events) == 2
    assert all(event["id"] not in previous_ids for event in latest_events)
    assert {
        event["entity_id"] for event in latest_events
    } == {"flow-1", "flow-2"}

def test_step_preserves_flow_count(simulation):
    simulation.step()

    assert len(simulation.traffic_engine.all_flows()) == 2


def test_disabling_server_makes_its_flows_unreachable(simulation):
    simulation.topology.set_node_status("server-1", active=False)

    flows = simulation.traffic_engine.all_flows()

    server_flow = next(
        flow for flow in flows
        if flow["destination"] == "server-1"
    )

    assert server_flow["reachable"] is False
    assert server_flow["route"] is None


def test_disabling_a_link_can_change_the_route(simulation):
    simulation.topology.set_link_status(
        "router-1", "server-1", active=False
    )

    route = simulation.topology.shortest_path(
        "client-1", "server-1"
    )

    assert route == ["client-1", "switch-1", "server-1"]
    assert simulation.topology.path_latency(route) == 5.0
