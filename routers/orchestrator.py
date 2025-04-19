# routers/orchestrator.py

from fastapi import APIRouter, HTTPException
from clients import Nats, DB, Milvus
from loguru import logger

from models.orchestrator import Orchestrator

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])

@router.post("/run/{config_name}")
async def run_simulation(
    config_name: str,
    broker: Nats,
    db: DB,
    milvus: Milvus,
):
    """
    Given a saved configuration name, spins up a new simulation end‑to‑end:
      • Simulation record & NATS stream
      • World + regions + resources
      • Agents collections & DB rows
      • Emits NATS events at each step
    """
    orchestrator = Orchestrator(db=db, nats=broker, milvus=milvus)
    try:
        sim_id = await orchestrator.run_from_config(config_name)
    except ValueError as e:
        logger.error(f"Orchestrator error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during orchestration")
        raise HTTPException(status_code=500, detail="Internal orchestration error")

    return {"simulation_id": sim_id, "message": "Simulation started successfully."}
