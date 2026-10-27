
"""LLM-planned Red Agent for the NetMind simulator."""

from __future__ import annotations

import json
from typing import Any

from backend.agents.ollama_client import OllamaClient
from backend.network.simulation import SimulationController


class RedAgent:
    """Plan with Qwen, validate the plan, then execute in simulation."""

    SCENARIOS = {
        "link_disruption": {
            "description": (
                "Disable the simulated link between router-1 and server-1. "
                "The redundant route may preserve connectivity."
            ),
            "target": "router-1<->server-1",
        },
        "server_disruption": {
            "description": (
                "Disable simulated server-1 and measure the effect on "
                "flows destined for that server."
            ),
            "target": "server-1",
        },
    }

    SYSTEM_PROMPT = """
You are NetMindAI's Red Agent scenario planner.

Your task is to SELECT exactly one permitted scenario.
You must make a decision, not repeat the input.

Return ONLY a JSON object in this exact format:
{
  "scenario_id": "link_disruption",
  "rationale": "A short reason for choosing the scenario"
}

Choose exactly one ID from the allowed_scenario_ids list.
Use the goal and network summary to make your choice.
Do not return the input, network state, or allowed-scenarios object.
Do not claim the scenario has been executed.
"""

    def __init__(
        self,
        simulation: SimulationController,
        llm: OllamaClient | None = None,
    ) -> None:
        self.simulation = simulation
        self.llm = llm or OllamaClient()

    def plan(self, goal: str = "Test network resilience") -> dict[str, Any]:
        """Ask Qwen to choose a scenario using the current network state."""
        if not goal.strip():
            raise ValueError("Planning goal cannot be empty.")

        snapshot = self.simulation.snapshot()

        # Send only the information needed for scenario selection.
        network_summary = {
            "nodes": [
                {
                    "id": node["id"],
                    "type": node["type"],
                    "active": node["active"],
                }
                for node in snapshot["topology"]["nodes"]
            ],
            "links": [
                {
                    "source": link["source"],
                    "target": link["target"],
                    "active": link["active"],
                }
                for link in snapshot["topology"]["links"]
            ],
            "flows": [
                {
                    "id": flow["id"],
                    "destination": flow["destination"],
                    "active": flow["active"],
                    "reachable": flow["reachable"],
                }
                for flow in snapshot["flows"]
            ],
        }

        prompt = json.dumps(
            {
                "goal": goal,
                "network_summary": network_summary,
                "allowed_scenario_ids": list(self.SCENARIOS.keys()),
                "decision_instruction": (
                    "Choose the single scenario that best tests network "
                    "resilience. Prefer link_disruption when testing "
                    "redundant-path failover. Prefer server_disruption "
                    "when testing loss of a server."
                ),
            },
            ensure_ascii=False,
        )

        decision = self.llm.chat_json(self.SYSTEM_PROMPT, prompt)

        # Treat all model output as untrusted input.
        scenario_id = decision.get("scenario_id")
        rationale = decision.get("rationale")

        if not isinstance(scenario_id, str) or scenario_id not in self.SCENARIOS:
            raise ValueError(
                f"Qwen proposed unsupported scenario: {scenario_id!r}"
            )

        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("Qwen's plan must include a rationale.")

        return {
            "scenario_id": scenario_id,
            "rationale": rationale.strip(),
            "planner_model": self.llm.model,
        }

    def execute_planned(
        self,
        goal: str = "Test network resilience",
    ) -> dict[str, Any]:
        """Plan with Qwen, then execute only a validated scenario."""
        plan = self.plan(goal)
        result = self.execute(plan["scenario_id"])
        result["plan"] = plan
        return result

    def execute(
        self,
        scenario_id: str = "link_disruption",
    ) -> dict[str, Any]:
        """Execute an allowlisted scenario inside the simulator."""
        if scenario_id not in self.SCENARIOS:
            raise ValueError(
                f"Unsupported scenario {scenario_id!r}. "
                f"Supported scenarios: {', '.join(self.SCENARIOS)}."
            )

        topology = self.simulation.topology

        if scenario_id == "link_disruption":
            source, target = "router-1", "server-1"

            link = next(
                (
                    item
                    for item in topology.links
                    if {item.source, item.target} == {source, target}
                ),
                None,
            )

            if link is None:
                raise ValueError(
                    f"Required demo link {source}<->{target} is missing."
                )

            if not link.active:
                raise RuntimeError(
                    "Target link is already disabled. Reset the simulation."
                )

            route_before = topology.shortest_path("client-1", "server-1")
            if route_before is None:
                raise RuntimeError(
                    "Target is already unreachable; reset the simulation."
                )

            topology.set_link_status(source, target, active=False)
            route_after = topology.shortest_path("client-1", "server-1")

            target_id = f"{source}<->{target}"
            action = "disable_simulated_link"

        else:
            target_id = "server-1"
            server = topology.get_node(target_id)

            if not server.active:
                raise RuntimeError(
                    "Target server is already disabled. Reset the simulation."
                )

            route_before = topology.shortest_path("client-1", target_id)
            if route_before is None:
                raise RuntimeError(
                    "Target is already unreachable; reset the simulation."
                )

            topology.set_node_status(target_id, active=False)
            route_after = topology.shortest_path("client-1", target_id)

            action = "disable_simulated_node"

        result: dict[str, Any] = {
            "scenario_id": scenario_id,
            "status": "executed",
            "action": action,
            "target": target_id,
            "route_before": route_before,
            "route_after": route_after,
            "disruption_active": True,
            "simulation_step": self.simulation.step_number,
        }

        self.simulation.telemetry.record_event(
            event_type="red_scenario_executed",
            message=(
                f"Red Agent executed {scenario_id} against {target_id}; "
                f"destination is "
                f"{'reachable' if route_after else 'unreachable'}."
            ),
            severity="warning",
            source="red_agent",
            entity_id=target_id,
            details=result,
        )

        return result
