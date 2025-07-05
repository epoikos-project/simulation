# routers/orchestrator.py


from fastapi import APIRouter, HTTPException
from loguru import logger

from clients import Nats, TinyDB, db
from clients.db import DB

from services.orchestrator import OrchestratorService

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])


@router.post("/initialize/{config_name}")
async def run(config_name: str, tinydb: TinyDB, db: DB, nats: Nats):
    orch = OrchestratorService(tinydb=tinydb, db=db, nats=nats)
    try:
        sim_id = await orch.run_from_config(config_name)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to run. Check Server logs")
    return {"simulation_id": sim_id}


@router.post("/tick/{simulation_id}")
async def tick(simulation_id: str, tinydb: TinyDB, db: DB, nats: Nats):
    orch = OrchestratorService(tinydb=tinydb, db=db, nats=nats)
    try:
        await orch.tick(simulation_id)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to tick: {e}")
    return {"message": f"Tick for simulation {simulation_id} completed"}


@router.post("/start/{simulation_id}")
async def start(simulation_id: str, tinydb: TinyDB, db: DB, nats: Nats):
    orch = OrchestratorService(tinydb=tinydb, db=db, nats=nats)
    try:
        await orch.start(simulation_id)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to start: {e}")
    return {"message": f"Simulation {simulation_id} started"}


@router.post("/stop/{simulation_id}")
async def stop(simulation_id: str, tinydb: TinyDB, db: DB, nats: Nats):
    orch = OrchestratorService(tinydb=tinydb, db=db, nats=nats)
    try:
        await orch.stop(simulation_id)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to stop: {e}")
    return {"message": f"Simulation {simulation_id} stopped"}
