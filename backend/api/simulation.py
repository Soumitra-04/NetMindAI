
from fastapi import APIRouter

from backend.network.simulation import SimulationController

router = APIRouter()

simulation = SimulationController.create_demo()


@router.get("/state")
def get_simulation_state():
    return simulation.snapshot()


@router.post("/step")
def advance_simulation():
    return simulation.step()


@router.post("/reset")
def reset_simulation():
    global simulation
    simulation = SimulationController.create_demo()
    return simulation.snapshot()
