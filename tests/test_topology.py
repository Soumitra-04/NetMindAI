
import pytest

from backend.network.topology import (
    NODE_TYPES,
    NetworkLink,
    NetworkNode,
    NetworkTopology,
    create_demo_topology,
)


@pytest.fixture
def topology():
    return create_demo_topology()


@pytest.fixture
def small_graph():
    """A predictable graph for routing tests."""
    graph = NetworkTopology()

    for node_id in ("A", "B", "C", "D"):
        graph.add_node(NetworkNode(node_id, node_id, "host"))

    graph.add_link(NetworkLink("A", "B", latency_ms=2))
    graph.add_link(NetworkLink("B", "D", latency_ms=3))
    graph.add_link(NetworkLink("A", "C", latency_ms=1))
    graph.add_link(NetworkLink("C", "D", latency_ms=10))

    return graph


# -------------------------------------------------------------------
# Node validation
# -------------------------------------------------------------------

@pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
def test_all_supported_node_types_are_accepted(node_type):
    node = NetworkNode("n1", "Node 1", node_type)
    assert node.type == node_type


@pytest.mark.parametrize("node_id,name", [
    ("", "Node"),
    ("   ", "Node"),
    ("n1", ""),
    ("n1", "   "),
])
def test_node_rejects_blank_id_or_name(node_id, name):
    with pytest.raises(ValueError):
        NetworkNode(node_id, name, "host")


def test_node_rejects_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported node type"):
        NetworkNode("n1", "Node", "modem")


def test_node_defaults_and_metadata():
    node = NetworkNode("n1", "Node", "host")

    assert node.active is True
    assert node.ip_address is None
    assert node.metadata == {}


def test_node_metadata_is_independent():
    first = NetworkNode("n1", "First", "host")
    second = NetworkNode("n2", "Second", "host")

    first.metadata["region"] = "lab"

    assert second.metadata == {}


# -------------------------------------------------------------------
# Link validation
# -------------------------------------------------------------------

def test_link_defaults():
    link = NetworkLink("A", "B")

    assert link.latency_ms == 1.0
    assert link.bandwidth_mbps == 100.0
    assert link.packet_loss_pct == 0.0
    assert link.active is True


def test_link_rejects_self_connection():
    with pytest.raises(ValueError, match="itself"):
        NetworkLink("A", "A")


@pytest.mark.parametrize("latency", [-1, -0.1])
def test_link_rejects_negative_latency(latency):
    with pytest.raises(ValueError, match="Latency"):
        NetworkLink("A", "B", latency_ms=latency)


def test_link_accepts_zero_latency():
    link = NetworkLink("A", "B", latency_ms=0)
    assert link.latency_ms == 0


@pytest.mark.parametrize("bandwidth", [0, -1, -0.1])
def test_link_rejects_nonpositive_bandwidth(bandwidth):
    with pytest.raises(ValueError, match="Bandwidth"):
        NetworkLink("A", "B", bandwidth_mbps=bandwidth)


@pytest.mark.parametrize("loss", [-0.1, 100.1, -1, 101])
def test_link_rejects_invalid_packet_loss(loss):
    with pytest.raises(ValueError, match="Packet loss"):
        NetworkLink("A", "B", packet_loss_pct=loss)


@pytest.mark.parametrize("loss", [0, 50, 100])
def test_link_accepts_packet_loss_boundaries(loss):
    link = NetworkLink("A", "B", packet_loss_pct=loss)
    assert link.packet_loss_pct == loss


# -------------------------------------------------------------------
# Topology mutations and lookups
# -------------------------------------------------------------------

def test_add_and_get_node():
    graph = NetworkTopology()
    node = NetworkNode("A", "Alpha", "host")

    graph.add_node(node)

    assert graph.get_node("A") is node


def test_duplicate_node_is_rejected():
    graph = NetworkTopology()
    graph.add_node(NetworkNode("A", "Alpha", "host"))

    with pytest.raises(ValueError, match="already exists"):
        graph.add_node(NetworkNode("A", "Another Alpha", "router"))


def test_unknown_node_lookup_raises_helpful_error():
    graph = NetworkTopology()

    with pytest.raises(KeyError, match="does not exist"):
        graph.get_node("missing")


def test_add_link_requires_existing_source():
    graph = NetworkTopology()
    graph.add_node(NetworkNode("B", "Beta", "host"))

    with pytest.raises(ValueError, match="Unknown source"):
        graph.add_link(NetworkLink("A", "B"))


def test_add_link_requires_existing_target():
    graph = NetworkTopology()
    graph.add_node(NetworkNode("A", "Alpha", "host"))

    with pytest.raises(ValueError, match="Unknown target"):
        graph.add_link(NetworkLink("A", "B"))


def test_duplicate_link_is_rejected_even_in_reverse_order():
    graph = NetworkTopology()
    graph.add_node(NetworkNode("A", "Alpha", "host"))
    graph.add_node(NetworkNode("B", "Beta", "host"))

    graph.add_link(NetworkLink("A", "B"))

    with pytest.raises(ValueError, match="already exists"):
        graph.add_link(NetworkLink("B", "A"))


# -------------------------------------------------------------------
# Neighbor discovery
# -------------------------------------------------------------------

def test_neighbors_are_bidirectional(topology):
    neighbors = topology.get_neighbors("client-1")

    assert [node.id for node, _ in neighbors] == ["switch-1"]


def test_neighbors_include_only_active_links(topology):
    topology.set_link_status("client-1", "switch-1", False)

    assert topology.get_neighbors("client-1") == []


def test_neighbors_exclude_inactive_neighbor_nodes(topology):
    topology.set_node_status("switch-1", False)

    assert topology.get_neighbors("client-1") == []


def test_inactive_node_has_no_neighbors(topology):
    topology.set_node_status("client-1", False)

    assert topology.get_neighbors("client-1") == []


def test_neighbors_reject_unknown_node(topology):
    with pytest.raises(KeyError):
        topology.get_neighbors("missing")


# -------------------------------------------------------------------
# Shortest path
# -------------------------------------------------------------------

def test_demo_topology_has_expected_shortest_path(topology):
    path = topology.shortest_path("client-1", "server-1")

    assert path == ["client-1", "switch-1", "server-1"]
    assert topology.path_latency(path) == pytest.approx(5.0)


def test_shortest_path_chooses_lowest_latency(small_graph):
    path = small_graph.shortest_path("A", "D")

    assert path == ["A", "B", "D"]
    assert small_graph.path_latency(path) == pytest.approx(5.0)


def test_shortest_path_is_bidirectional(small_graph):
    assert small_graph.shortest_path("D", "A") == [
        "D", "B", "A"
    ]


def test_shortest_path_returns_single_node_for_same_endpoint(topology):
    assert topology.shortest_path("client-1", "client-1") == [
        "client-1"
    ]


def test_shortest_path_returns_none_for_disconnected_nodes(topology):
    assert topology.shortest_path("client-1", "firewall-1") is not None

    # Disconnect the firewall from both of its neighbors.
    topology.set_link_status("router-1", "firewall-1", False)
    topology.set_link_status("firewall-1", "server-2", False)

    assert topology.shortest_path("client-1", "firewall-1") is None


def test_shortest_path_returns_none_for_inactive_source(topology):
    topology.set_node_status("client-1", False)

    assert topology.shortest_path("client-1", "server-1") is None


def test_shortest_path_returns_none_for_inactive_target(topology):
    topology.set_node_status("server-1", False)

    assert topology.shortest_path("client-1", "server-1") is None


def test_shortest_path_rejects_unknown_source(topology):
    with pytest.raises(KeyError):
        topology.shortest_path("missing", "server-1")


def test_shortest_path_rejects_unknown_target(topology):
    with pytest.raises(KeyError):
        topology.shortest_path("client-1", "missing")


def test_shortest_path_recalculates_after_link_failure(topology):
    original = topology.shortest_path("client-1", "server-1")
    assert original == ["client-1", "switch-1", "server-1"]

    topology.set_link_status("switch-1", "server-1", False)

    alternate = topology.shortest_path("client-1", "server-1")

    assert alternate == [
        "client-1",
        "switch-1",
        "router-1",
        "server-1",
    ]
    assert topology.path_latency(alternate) == pytest.approx(6.0)


def test_shortest_path_uses_latency_not_bandwidth():
    graph = NetworkTopology()

    for node_id in ("A", "B", "C", "D"):
        graph.add_node(NetworkNode(node_id, node_id, "host"))

    graph.add_link(
        NetworkLink("A", "B", latency_ms=1, bandwidth_mbps=1)
    )
    graph.add_link(
        NetworkLink("B", "D", latency_ms=1, bandwidth_mbps=1)
    )
    graph.add_link(
        NetworkLink("A", "C", latency_ms=2, bandwidth_mbps=1000)
    )
    graph.add_link(
        NetworkLink("C", "D", latency_ms=2, bandwidth_mbps=1000)
    )

    assert graph.shortest_path("A", "D") == ["A", "B", "D"]


def test_shortest_path_handles_zero_latency_links():
    graph = NetworkTopology()
    graph.add_node(NetworkNode("A", "Alpha", "host"))
    graph.add_node(NetworkNode("B", "Beta", "host"))
    graph.add_link(NetworkLink("A", "B", latency_ms=0))

    assert graph.shortest_path("A", "B") == ["A", "B"]
    assert graph.path_latency(["A", "B"]) == 0


# -------------------------------------------------------------------
# Path latency validation
# -------------------------------------------------------------------

def test_path_latency_for_single_node(topology):
    assert topology.path_latency(["client-1"]) == 0


def test_path_latency_for_empty_path(topology):
    assert topology.path_latency([]) == 0


def test_path_latency_rejects_unknown_single_node(topology):
    with pytest.raises(KeyError):
        topology.path_latency(["missing"])


def test_path_latency_sums_all_links(topology):
    path = topology.shortest_path("client-1", "server-1")

    assert topology.path_latency(path) == pytest.approx(5.0)


def test_path_latency_accepts_reverse_path(topology):
    path = ["server-1", "router-1", "switch-1", "client-1"]

    assert topology.path_latency(path) == pytest.approx(6.0)


def test_path_latency_rejects_missing_active_link(topology):
    topology.set_link_status("switch-1", "router-1", False)

    with pytest.raises(ValueError, match="No active link"):
        topology.path_latency(
            ["client-1", "switch-1", "router-1"]
        )


def test_path_latency_rejects_nonexistent_link(topology):
    with pytest.raises(ValueError, match="No active link"):
        topology.path_latency(["client-1", "server-2"])


# -------------------------------------------------------------------
# Status changes
# -------------------------------------------------------------------

def test_set_node_status_changes_node_state(topology):
    topology.set_node_status("server-1", False)

    assert topology.get_node("server-1").active is False

    topology.set_node_status("server-1", True)
    assert topology.get_node("server-1").active is True


def test_set_node_status_rejects_unknown_node(topology):
    with pytest.raises(KeyError):
        topology.set_node_status("missing", False)


def test_set_link_status_works_in_reverse_order(topology):
    topology.set_link_status("switch-1", "client-1", False)

    assert topology.get_neighbors("client-1") == []


def test_set_link_status_rejects_missing_link(topology):
    with pytest.raises(KeyError, match="No link exists"):
        topology.set_link_status("client-1", "server-2", False)


# -------------------------------------------------------------------
# Snapshot and demo topology
# -------------------------------------------------------------------

def test_snapshot_contains_json_friendly_nodes_and_links(topology):
    snapshot = topology.snapshot()

    assert len(snapshot["nodes"]) == 6
    assert len(snapshot["links"]) == 7
    assert snapshot["nodes"][0]["id"] == "client-1"
    assert snapshot["links"][0]["source"] == "client-1"
    assert snapshot["links"][0]["target"] == "switch-1"


def test_snapshot_does_not_mutate_topology(topology):
    topology.snapshot()

    assert len(topology.nodes) == 6
    assert len(topology.links) == 7


def test_demo_topology_contains_expected_devices(topology):
    assert set(topology.nodes) == {
        "client-1",
        "router-1",
        "switch-1",
        "server-1",
        "server-2",
        "firewall-1",
    }


def test_demo_topology_routes_to_both_servers(topology):
    assert topology.shortest_path("client-1", "server-1") is not None
    assert topology.shortest_path("client-1", "server-2") is not None
