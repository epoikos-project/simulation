# routers/orchestrator.py

from fastapi import APIRouter, HTTPException
from loguru import logger
from clients import Nats, DB, Milvus
from clients import sqlite
from clients.sqlite import DB as SQLiteDB
from models.orchestrator import Orchestrator

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])


@router.post("/initialize/{config_name}")
async def run(config_name: str, db: DB, sqlite: SQLiteDB, nats: Nats):
    orch = Orchestrator(db=db, sqlite=sqlite, nats=nats)
    try:
        sim_id = await orch.run_from_config(config_name)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to run. Check Server logs")
    return {"simulation_id": sim_id}


@router.post("/tick/{simulation_id}")
async def tick(simulation_id: str, db: DB, sqlite: SQLiteDB, nats: Nats):
    orch = Orchestrator(db=db, sqlite=sqlite, nats=nats)
    try:
        await orch.tick(simulation_id)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"Failed to tick: {e}")
    return {"message": f"Tick for simulation {simulation_id} completed"}


@router.post("/start/{simulation_id}")
async def start(simulation_id: str, db: DB, nats: Nats):
    orch = Orchestrator(db=db, nats=nats)
    try:
        await orch.start(simulation_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {e}")
    return {"message": f"Simulation {simulation_id} started"}


@router.post("/stop/{simulation_id}")
async def stop(simulation_id: str, db: DB, nats: Nats):
    orch = Orchestrator(db=db, nats=nats)
    try:
        await orch.stop(simulation_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to stop: {e}")
    return {"message": f"Simulation {simulation_id} stopped"}
