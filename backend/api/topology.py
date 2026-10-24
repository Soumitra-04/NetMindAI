
from fastapi import APIRouter

from backend.api.simulation import simulation

router = APIRouter()


@router.get("/")
def get_topology():
    return simulation.topology.snapshot()
