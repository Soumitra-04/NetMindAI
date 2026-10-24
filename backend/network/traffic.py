
"""Traffic-flow models for the NetMind network simulator."""

from dataclasses import asdict, dataclass
from typing import Any

from backend.network.topology import NetworkTopology


SUPPORTED_PROTOCOLS = {"TCP", "UDP", "ICMP"}


@dataclass
class TrafficFlow:
    """A simulated flow of traffic between two network nodes."""

    id: str
    source: str
    destination: str
    protocol: str = "TCP"
    packets_per_second: float = 100.0
    packet_size_bytes: int = 1000
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Flow ID cannot be empty.")

        if self.source == self.destination:
            raise ValueError("Source and destination must differ.")

        self.protocol = self.protocol.upper()

        if self.protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported protocol '{self.protocol}'. "
                f"Choose from: {sorted(SUPPORTED_PROTOCOLS)}"
            )

        if self.packets_per_second < 0:
            raise ValueError("Packet rate cannot be negative.")

        if self.packet_size_bytes <= 0:
            raise ValueError("Packet size must be greater than zero.")

    @property
    def offered_mbps(self) -> float:
        """Calculate the offered traffic rate in megabits per second."""
        bits_per_second = (
            self.packets_per_second * self.packet_size_bytes * 8
        )
        return bits_per_second / 1_000_000


class TrafficEngine:
    """Manage simulated traffic flows over a network topology."""

    def __init__(self, topology: NetworkTopology) -> None:
        self.topology = topology
        self.flows: dict[str, TrafficFlow] = {}

    def add_flow(self, flow: TrafficFlow) -> None:
        """Register a flow after validating its endpoints."""
        if flow.id in self.flows:
            raise ValueError(f"Flow '{flow.id}' already exists.")

        self.topology.get_node(flow.source)
        self.topology.get_node(flow.destination)

        self.flows[flow.id] = flow

    def get_route(self, flow_id: str) -> list[str] | None:
        """Find the current route for a flow."""
        flow = self._get_flow(flow_id)

        if not flow.active:
            return None

        return self.topology.shortest_path(
            flow.source,
            flow.destination,
        )

    def flow_summary(self, flow_id: str) -> dict[str, Any]:
        """Return flow details and its current route and latency."""
        flow = self._get_flow(flow_id)
        route = self.get_route(flow_id)

        latency_ms = (
            self.topology.path_latency(route)
            if route is not None
            else None
        )

        return {
            **asdict(flow),
            "offered_mbps": flow.offered_mbps,
            "route": route,
            "path_latency_ms": latency_ms,
            "reachable": route is not None,
        }

    def all_flows(self) -> list[dict[str, Any]]:
        """Return summaries of every registered flow."""
        return [
            self.flow_summary(flow_id)
            for flow_id in self.flows
        ]

    def total_offered_mbps(self) -> float:
        """Sum the offered rates of all active flows."""
        return sum(
            flow.offered_mbps
            for flow in self.flows.values()
            if flow.active
        )

    def _get_flow(self, flow_id: str) -> TrafficFlow:
        try:
            return self.flows[flow_id]
        except KeyError:
            raise KeyError(
                f"Traffic flow '{flow_id}' does not exist."
            ) from None
