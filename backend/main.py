from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.topology import router as topology_router
from backend.api.simulation import router as simulation_router
from backend.api.events import router as events_router
from backend.api.blue import router as blue_router
from backend.api.orchestration import router as orchestration_router

app = FastAPI(
    title="NetMind API",
    description="Network simulation and AI-driven security",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topology_router, prefix="/topology", tags=["Topology"])
app.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])
app.include_router(events_router, prefix="/events", tags=["Events"])
app.include_router(blue_router, prefix="/blue", tags=["Blue Agent"])
app.include_router(orchestration_router, prefix="/orchestration", tags=["Orchestration"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
