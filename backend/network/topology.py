
"""Network topology model for the NetMind simulation engine.

Models network nodes and bidirectional links, validates topology changes,
and calculates shortest paths using Dijkstra's algorithm.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from heapq import heappop, heappush
from itertools import count
from typing import Any


NODE_TYPES = {"host", "router", "switch", "server", "firewall"}


@dataclass
class NetworkNode:
    """A device in the simulated network."""

    id: str
    name: str
    type: str
    ip_address: str | None = None
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Node ID cannot be empty.")
        if not self.name.strip():
            raise ValueError("Node name cannot be empty.")
        if self.type not in NODE_TYPES:
            raise ValueError(
                f"Unsupported node type '{self.type}'. "
                f"Choose from: {sorted(NODE_TYPES)}"
            )


@dataclass
class NetworkLink:
    """A bidirectional connection between two network nodes."""

    source: str
    target: str
    latency_ms: float = 1.0
    bandwidth_mbps: float = 100.0
    packet_loss_pct: float = 0.0
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source == self.target:
            raise ValueError("A link cannot connect a node to itself.")
        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative.")
        if self.bandwidth_mbps <= 0:
            raise ValueError("Bandwidth must be greater than zero.")
        if not 0 <= self.packet_loss_pct <= 100:
            raise ValueError("Packet loss must be between 0 and 100.")


class NetworkTopology:
    """In-memory network graph with bidirectional links and pathfinding."""

    def __init__(self) -> None:
        self.nodes: dict[str, NetworkNode] = {}
        self.links: list[NetworkLink] = []

    def add_node(self, node: NetworkNode) -> None:
        """Add a node, rejecting duplicate IDs."""
        if node.id in self.nodes:
            raise ValueError(f"Node '{node.id}' already exists.")
        self.nodes[node.id] = node

    def add_link(self, link: NetworkLink) -> None:
        """Connect two existing nodes with a bidirectional link."""
        if link.source not in self.nodes:
            raise ValueError(f"Unknown source node '{link.source}'.")
        if link.target not in self.nodes:
            raise ValueError(f"Unknown target node '{link.target}'.")

        duplicate = any(
            {existing.source, existing.target} == {link.source, link.target}
            for existing in self.links
        )
        if duplicate:
            raise ValueError(
                f"A link between '{link.source}' and '{link.target}' "
                "already exists."
            )

        self.links.append(link)

    def get_node(self, node_id: str) -> NetworkNode:
        """Return a node or raise an informative error."""
        try:
            return self.nodes[node_id]
        except KeyError:
            raise KeyError(
                f"Network node '{node_id}' does not exist."
            ) from None

    def get_neighbors(
        self, node_id: str
    ) -> list[tuple[NetworkNode, NetworkLink]]:
        """Return active neighboring nodes and their connecting links."""
        node = self.get_node(node_id)

        if not node.active:
            return []

        neighbors: list[tuple[NetworkNode, NetworkLink]] = []

        for link in self.links:
            if not link.active:
                continue

            if link.source == node_id:
                neighbor_id = link.target
            elif link.target == node_id:
                neighbor_id = link.source
            else:
                continue

            neighbor = self.nodes[neighbor_id]

            if neighbor.active:
                neighbors.append((neighbor, link))

        return neighbors

    def shortest_path(self, source: str, target: str) -> list[str] | None:
        """Find the lowest-latency path using Dijkstra's algorithm.

        Returns node IDs including source and target, or None if unreachable.
        """
        self.get_node(source)
        self.get_node(target)

        if not self.nodes[source].active or not self.nodes[target].active:
            return None

        if source == target:
            return [source]

        distances = {node_id: float("inf") for node_id in self.nodes}
        previous: dict[str, str] = {}
        distances[source] = 0.0

        sequence = count()
        queue: list[tuple[float, int, str]] = [
            (0.0, next(sequence), source)
        ]

        while queue:
            current_distance, _, current = heappop(queue)

            if current_distance > distances[current]:
                continue

            if current == target:
                break

            for neighbor, link in self.get_neighbors(current):
                candidate = current_distance + link.latency_ms

                if candidate < distances[neighbor.id]:
                    distances[neighbor.id] = candidate
                    previous[neighbor.id] = current

                    heappush(
                        queue,
                        (candidate, next(sequence), neighbor.id),
                    )

        if distances[target] == float("inf"):
            return None

        path = [target]

        while path[-1] != source:
            path.append(previous[path[-1]])

        path.reverse()
        return path

    def path_latency(self, path: list[str]) -> float:
        """Calculate latency for a path using active links."""
        if not path:
            return 0.0

        for node_id in path:
            self.get_node(node_id)

        if len(path) == 1:
            return 0.0

        total_latency = 0.0

        for source, target in zip(path, path[1:]):
            link = next(
                (
                    candidate
                    for candidate in self.links
                    if {candidate.source, candidate.target} == {source, target}
                    and candidate.active
                ),
                None,
            )

            if link is None:
                raise ValueError(
                    f"No active link exists between '{source}' and '{target}'."
                )

            total_latency += link.latency_ms

        return total_latency

    def set_node_status(self, node_id: str, active: bool) -> None:
        """Enable or disable a network node."""
        self.get_node(node_id).active = active

    def set_link_status(
        self, source: str, target: str, active: bool
    ) -> None:
        """Enable or disable a connection, regardless of endpoint order."""
        for link in self.links:
            if {link.source, link.target} == {source, target}:
                link.active = active
                return

        raise KeyError(
            f"No link exists between '{source}' and '{target}'."
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly topology representation."""
        return {
            "nodes": [asdict(node) for node in self.nodes.values()],
            "links": [asdict(link) for link in self.links],
        }


def create_demo_topology() -> NetworkTopology:
    """Create a demo network with redundant connectivity for failover tests."""
    topology = NetworkTopology()

    demo_nodes = [
        NetworkNode("client-1", "Client 1", "host", "10.0.0.10"),
        NetworkNode("router-1", "Core Router", "router", "10.0.0.1"),
        NetworkNode("switch-1", "Access Switch", "switch"),
        NetworkNode("server-1", "Application Server", "server", "10.0.0.100"),
        NetworkNode("server-2", "Backup Server", "server", "10.0.0.101"),
        NetworkNode("firewall-1", "Edge Firewall", "firewall"),
    ]

    for node in demo_nodes:
        topology.add_node(node)

    demo_links = [
        NetworkLink("client-1", "switch-1", latency_ms=1.0),
        NetworkLink("switch-1", "router-1", latency_ms=2.0),
        NetworkLink("router-1", "server-1", latency_ms=3.0),
        NetworkLink("router-1", "server-2", latency_ms=5.0),
        NetworkLink("router-1", "firewall-1", latency_ms=1.5),
        NetworkLink("firewall-1", "server-2", latency_ms=2.0),

        # Redundant path to server-1 for link-failure recovery.
        NetworkLink("switch-1", "server-1", latency_ms=4.0),
    ]

    for link in demo_links:
        topology.add_link(link)

    return topology
