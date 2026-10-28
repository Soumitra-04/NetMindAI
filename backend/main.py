from fastapi import FastAPI

from backend.api.topology import router as topology_router
from backend.api.simulation import router as simulation_router
from backend.api.events import router as events_router
from backend.api.blue import router as blue_router

app = FastAPI(
    title="NetMind API",
    description="Network simulation and AI-driven security",
    version="0.1.0",
)

app.include_router(topology_router, prefix="/topology", tags=["Topology"])
app.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])
app.include_router(events_router, prefix="/events", tags=["Events"])
app.include_router(blue_router, prefix="/blue", tags=["Blue Agent"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
