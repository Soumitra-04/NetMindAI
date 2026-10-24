
import pytest

from backend.network.topology import (
    NetworkLink,
    NetworkNode,
    NetworkTopology,
    create_demo_topology,
)
from backend.network.traffic import (
    SUPPORTED_PROTOCOLS,
    TrafficEngine,
    TrafficFlow,
)


@pytest.fixture
def topology():
    return create_demo_topology()


@pytest.fixture
def engine(topology):
    return TrafficEngine(topology)


@pytest.fixture
def flow():
    return TrafficFlow(
        id="flow-001",
        source="client-1",
        destination="server-1",
        protocol="TCP",
        packets_per_second=100,
        packet_size_bytes=1000,
    )


@pytest.fixture
def registered_engine(engine, flow):
    engine.add_flow(flow)
    return engine


# -------------------------------------------------------------------
# TrafficFlow validation
# -------------------------------------------------------------------

def test_flow_defaults():
    flow = TrafficFlow("f1", "A", "B")

    assert flow.protocol == "TCP"
    assert flow.packets_per_second == 100.0
    assert flow.packet_size_bytes == 1000
    assert flow.active is True


@pytest.mark.parametrize("flow_id", ["", "   "])
def test_flow_rejects_blank_id(flow_id):
    with pytest.raises(ValueError, match="Flow ID"):
        TrafficFlow(flow_id, "A", "B")


def test_flow_rejects_identical_endpoints():
    with pytest.raises(ValueError, match="must differ"):
        TrafficFlow("f1", "A", "A")


@pytest.mark.parametrize("protocol", sorted(SUPPORTED_PROTOCOLS))
def test_flow_accepts_supported_protocols(protocol):
    flow = TrafficFlow("f1", "A", "B", protocol=protocol)

    assert flow.protocol == protocol


@pytest.mark.parametrize("protocol", ["tcp", "udp", "icmp", "TcP"])
def test_flow_normalizes_protocol_case(protocol):
    flow = TrafficFlow("f1", "A", "B", protocol=protocol)

    assert flow.protocol == protocol.upper()


def test_flow_rejects_unsupported_protocol():
    with pytest.raises(ValueError, match="Unsupported protocol"):
        TrafficFlow("f1", "A", "B", protocol="HTTP")


@pytest.mark.parametrize("rate", [-1, -0.1])
def test_flow_rejects_negative_packet_rate(rate):
    with pytest.raises(ValueError, match="Packet rate"):
        TrafficFlow(
            "f1", "A", "B",
            packets_per_second=rate,
        )


def test_flow_accepts_zero_packet_rate():
    flow = TrafficFlow(
        "f1", "A", "B",
        packets_per_second=0,
    )

    assert flow.packets_per_second == 0
    assert flow.offered_mbps == 0


@pytest.mark.parametrize("size", [0, -1])
def test_flow_rejects_nonpositive_packet_size(size):
    with pytest.raises(ValueError, match="Packet size"):
        TrafficFlow(
            "f1", "A", "B",
            packet_size_bytes=size,
        )


def test_flow_accepts_fractional_packet_rate():
    flow = TrafficFlow(
        "f1", "A", "B",
        packets_per_second=0.5,
    )

    assert flow.packets_per_second == 0.5


# -------------------------------------------------------------------
# Offered traffic calculation
# -------------------------------------------------------------------

def test_offered_mbps_calculation():
    flow = TrafficFlow(
        "f1", "A", "B",
        packets_per_second=100,
        packet_size_bytes=1000,
    )

    assert flow.offered_mbps == pytest.approx(0.8)


def test_offered_mbps_scales_with_packet_rate():
    low = TrafficFlow(
        "low", "A", "B",
        packets_per_second=100,
        packet_size_bytes=1000,
    )
    high = TrafficFlow(
        "high", "A", "B",
        packets_per_second=200,
        packet_size_bytes=1000,
    )

    assert high.offered_mbps == pytest.approx(
        2 * low.offered_mbps
    )


def test_offered_mbps_scales_with_packet_size():
    small = TrafficFlow(
        "small", "A", "B",
        packets_per_second=100,
        packet_size_bytes=500,
    )
    large = TrafficFlow(
        "large", "A", "B",
        packets_per_second=100,
        packet_size_bytes=1000,
    )

    assert large.offered_mbps == pytest.approx(
        2 * small.offered_mbps
    )


def test_offered_mbps_for_large_rate():
    flow = TrafficFlow(
        "f1", "A", "B",
        packets_per_second=1_000_000,
        packet_size_bytes=1500,
    )

    assert flow.offered_mbps == pytest.approx(12_000)


# -------------------------------------------------------------------
# Flow registration
# -------------------------------------------------------------------

def test_add_flow_registers_flow(engine, flow):
    engine.add_flow(flow)

    assert engine.flows["flow-001"] is flow


def test_add_flow_rejects_duplicate_id(engine, flow):
    engine.add_flow(flow)

    duplicate = TrafficFlow(
        "flow-001", "client-1", "server-2"
    )

    with pytest.raises(ValueError, match="already exists"):
        engine.add_flow(duplicate)


def test_add_flow_rejects_unknown_source(engine):
    flow = TrafficFlow("f1", "missing", "server-1")

    with pytest.raises(KeyError, match="does not exist"):
        engine.add_flow(flow)


def test_add_flow_rejects_unknown_destination(engine):
    flow = TrafficFlow("f1", "client-1", "missing")

    with pytest.raises(KeyError, match="does not exist"):
        engine.add_flow(flow)


def test_failed_registration_does_not_add_flow(engine):
    flow = TrafficFlow("f1", "missing", "server-1")

    with pytest.raises(KeyError):
        engine.add_flow(flow)

    assert engine.flows == {}


def test_engine_starts_without_flows(engine):
    assert engine.flows == {}
    assert engine.all_flows() == []
    assert engine.total_offered_mbps() == 0


# -------------------------------------------------------------------
# Route discovery
# -------------------------------------------------------------------

def test_get_route_returns_expected_path(registered_engine):
    assert registered_engine.get_route("flow-001") == [
        "client-1",
        "switch-1",
        "server-1",
]


def test_get_route_returns_none_for_inactive_flow(
    topology, flow
):
    engine = TrafficEngine(topology)
    flow.active = False
    engine.add_flow(flow)

    assert engine.get_route(flow.id) is None


def test_get_route_returns_none_when_destination_is_unreachable(
    topology, flow
):
    topology.set_link_status("switch-1", "router-1", False)
    topology.set_link_status("switch-1", "server-1", False)
    engine = TrafficEngine(topology)
    engine.add_flow(flow)

    assert engine.get_route(flow.id) is None


def test_get_route_reflects_topology_changes(
    topology, registered_engine
):
    assert registered_engine.get_route("flow-001") is not None

    topology.set_link_status("switch-1", "router-1", False)
    topology.set_link_status("switch-1", "server-1", False)
    assert registered_engine.get_route("flow-001") is None


def test_get_route_rejects_unknown_flow(engine):
    with pytest.raises(KeyError, match="does not exist"):
        engine.get_route("missing")


# -------------------------------------------------------------------
# Flow summaries
# -------------------------------------------------------------------

def test_flow_summary_contains_expected_fields(registered_engine):
    summary = registered_engine.flow_summary("flow-001")

    assert summary["id"] == "flow-001"
    assert summary["source"] == "client-1"
    assert summary["destination"] == "server-1"
    assert summary["protocol"] == "TCP"
    assert summary["active"] is True
    assert summary["reachable"] is True
    assert summary["offered_mbps"] == pytest.approx(0.8)
    assert summary["path_latency_ms"] == pytest.approx(5.0)
    assert summary["route"] == [
        "client-1",
        "switch-1",
        "server-1",
    ]


def test_inactive_flow_summary_has_no_route(
    topology, flow
):
    flow.active = False
    engine = TrafficEngine(topology)
    engine.add_flow(flow)

    summary = engine.flow_summary(flow.id)

    assert summary["active"] is False
    assert summary["route"] is None
    assert summary["path_latency_ms"] is None
    assert summary["reachable"] is False


def test_unreachable_flow_summary_has_no_route(
    topology, flow
):
    topology.set_link_status("switch-1", "router-1", False)
    topology.set_link_status("switch-1", "server-1", False)
    engine = TrafficEngine(topology)
    engine.add_flow(flow)

    summary = engine.flow_summary(flow.id)

    assert summary["active"] is True
    assert summary["route"] is None
    assert summary["path_latency_ms"] is None
    assert summary["reachable"] is False


def test_flow_summary_rejects_unknown_flow(engine):
    with pytest.raises(KeyError, match="does not exist"):
        engine.flow_summary("missing")


# -------------------------------------------------------------------
# All flows and aggregate traffic
# -------------------------------------------------------------------

def test_all_flows_returns_all_registered_summaries(
    registered_engine,
):
    summaries = registered_engine.all_flows()

    assert len(summaries) == 1
    assert summaries[0]["id"] == "flow-001"


def test_all_flows_returns_empty_list_for_empty_engine(engine):
    assert engine.all_flows() == []


def test_total_offered_mbps_sums_active_flows(
    registered_engine,
):
    registered_engine.add_flow(
        TrafficFlow(
            "flow-002",
            "client-1",
            "server-2",
            packets_per_second=200,
            packet_size_bytes=1000,
        )
    )

    assert registered_engine.total_offered_mbps() == pytest.approx(2.4)


def test_total_offered_mbps_excludes_inactive_flows(
    registered_engine,
):
    registered_engine.add_flow(
        TrafficFlow(
            "flow-002",
            "client-1",
            "server-2",
            packets_per_second=200,
            packet_size_bytes=1000,
            active=False,
        )
    )

    assert registered_engine.total_offered_mbps() == pytest.approx(0.8)


def test_total_offered_mbps_includes_active_unreachable_flows(
    topology,
):
    topology.set_link_status("switch-1", "router-1", False)
    engine = TrafficEngine(topology)

    engine.add_flow(
        TrafficFlow(
            "f1",
            "client-1",
            "server-1",
            packets_per_second=100,
            packet_size_bytes=1000,
        )
    )

    # The method sums active offered loads, regardless of reachability.
    assert engine.total_offered_mbps() == pytest.approx(0.8)


def test_total_offered_mbps_for_empty_engine(engine):
    assert engine.total_offered_mbps() == 0


# -------------------------------------------------------------------
# Isolation and status changes
# -------------------------------------------------------------------

def test_flow_summary_does_not_mutate_flow_fields(
    registered_engine,
):
    flow = registered_engine.flows["flow-001"]
    original_id = flow.id
    original_rate = flow.packets_per_second

    registered_engine.flow_summary(flow.id)

    assert flow.id == original_id
    assert flow.packets_per_second == original_rate


def test_disabling_node_makes_flow_unreachable(
    topology, registered_engine
):
    topology.set_node_status("server-1", False)

    summary = registered_engine.flow_summary("flow-001")

    assert summary["reachable"] is False
    assert summary["route"] is None
