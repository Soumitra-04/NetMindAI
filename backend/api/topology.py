from fastapi import APIRouter

from backend.api.simulation import simulation

router = APIRouter()


@router.get("/")
@router.get("", include_in_schema=False)
def get_topology():
    return simulation.topology.snapshot()
