
from fastapi import FastAPI

from backend.api.topology import router as topology_router
from backend.api.simulation import router as simulation_router

app = FastAPI(
    title="NetMind API",
    description="Network simulation and AI-driven security",
    version="0.1.0",
)

app.include_router(topology_router, prefix="/topology", tags=["Topology"])
app.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
