
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.network.telemetry import TelemetryCollector
from backend.network.topology import NetworkTopology, create_demo_topology
from backend.network.traffic import TrafficEngine, TrafficFlow


@dataclass
class SimulationController:
    topology: NetworkTopology
    traffic_engine: TrafficEngine
    telemetry: TelemetryCollector
    step_number: int = 0

    @classmethod
    def create_demo(cls) -> "SimulationController":
        topology = create_demo_topology()
        traffic_engine = TrafficEngine(topology)

        traffic_engine.add_flow(
            TrafficFlow(
                id="flow-1",
                source="client-1",
                destination="server-1",
                protocol="TCP",
                packets_per_second=100,
                packet_size_bytes=1000,
            )
        )
        traffic_engine.add_flow(
            TrafficFlow(
                id="flow-2",
                source="client-1",
                destination="server-2",
                protocol="UDP",
                packets_per_second=50,
                packet_size_bytes=1200,
            )
        )

        telemetry = TelemetryCollector(topology, traffic_engine)

        return cls(
            topology=topology,
            traffic_engine=traffic_engine,
            telemetry=telemetry,
        )

    def step(self) -> dict[str, Any]:
        """Advance the logical simulation by one step."""
        self.step_number += 1

        flows = self.traffic_engine.all_flows()
        for flow in flows:
            self.telemetry.record_flow_state(flow["id"])

        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return the current state for APIs and visualization."""
        return {
            "step_number": self.step_number,
            "topology": self.topology.snapshot(),
            "flows": self.traffic_engine.all_flows(),
            "metrics": self.telemetry.collect_metrics(),
        }
