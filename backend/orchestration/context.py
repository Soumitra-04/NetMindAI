"""Runtime context management for NetMind orchestration.

Decouples in-memory live Python objects (SimulationController, agent instances)
from checkpointed graph state to ensure state remains serializable and portable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Any, Callable

import backend.api.simulation as sim_mod
from backend.agents.blue_response import BlueResponse
from backend.agents.blue_sentinel import BlueSentinel
from backend.agents.ollama_client import OllamaClient
from backend.agents.red_agent import RedAgent
from backend.network.simulation import SimulationController


@dataclass
class RuntimeContext:
    """Live in-memory objects associated with a specific orchestration run."""

    simulation: SimulationController
    red_agent: RedAgent
    sentinel: BlueSentinel
    blue_response: BlueResponse
    llm: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeContextManager:
    """Thread-safe registry for live in-memory execution contexts.

    Lifecycle:
    - Contexts are registered when an orchestration run starts.
    - If a run uses a custom SimulationController, it is bound to run_id.
    - If no custom simulation is supplied, the active global simulation is used.
    - Contexts persist for the duration of the run and across approval interrupts.
    - Local limitation: In-memory contexts do not persist across process restarts.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, RuntimeContext] = {}
        self._lock = threading.Lock()

    def register_context(
        self,
        run_id: str,
        simulation: SimulationController | None = None,
        llm: Any | None = None,
        red_agent: RedAgent | None = None,
        sentinel: BlueSentinel | None = None,
        blue_response: BlueResponse | None = None,
    ) -> RuntimeContext:
        """Create or register live objects for a run."""
        sim = simulation or sim_mod.simulation
        resolved_llm = llm if llm is not None else None

        red = red_agent or RedAgent(sim, llm=resolved_llm)
        blue_sent = sentinel or BlueSentinel(sim, llm=resolved_llm)
        blue_resp = blue_response or BlueResponse(sim, llm=resolved_llm)

        ctx = RuntimeContext(
            simulation=sim,
            red_agent=red,
            sentinel=blue_sent,
            blue_response=blue_resp,
            llm=resolved_llm,
        )

        with self._lock:
            self._contexts[run_id] = ctx

        return ctx

    def get_context(self, run_id: str) -> RuntimeContext:
        """Retrieve the live context for a run, falling back to default simulation."""
        with self._lock:
            if run_id in self._contexts:
                return self._contexts[run_id]

        # Auto-initialize fallback context bound to active simulation
        return self.register_context(run_id)

    def cleanup_context(self, run_id: str) -> None:
        """Explicitly release in-memory references for a finalized run."""
        with self._lock:
            self._contexts.pop(run_id, None)

    def clear(self) -> None:
        """Clear all active contexts (primarily for test teardown)."""
        with self._lock:
            self._contexts.clear()


# Global runtime context manager instance
runtime_context_manager = RuntimeContextManager()
