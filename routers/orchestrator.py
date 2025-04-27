# routers/orchestrator.py

from fastapi import APIRouter, HTTPException
from clients import Nats, DB, Milvus
from models.orchestrator import Orchestrator

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])


@router.post("/initialize/{config_name}")
async def run(config_name: str, db: DB, nats: Nats, milvus: Milvus):
    orch = Orchestrator(db=db, nats=nats, milvus=milvus)
    try:
        sim_id = await orch.run_from_config(config_name)
    except Exception as e:
        raise HTTPException(500, f"Failed to run: {e}")
    return {"simulation_id": sim_id}


@router.post("/tick/{simulation_id}")
async def tick(simulation_id: str, db: DB, nats: Nats, milvus: Milvus):
    orch = Orchestrator(db=db, nats=nats, milvus=milvus)
    try:
        await orch.tick(simulation_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to tick: {e}")
    return {"message": f"Tick for simulation {simulation_id} completed"}


@router.post("/start/{simulation_id}")
async def start(simulation_id: str, db: DB, nats: Nats, milvus: Milvus):
    orch = Orchestrator(db=db, nats=nats, milvus=milvus)
    try:
        await orch.start(simulation_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {e}")
    return {"message": f"Simulation {simulation_id} started"}


@router.post("/stop/{simulation_id}")
async def stop(simulation_id: str, db: DB, nats: Nats, milvus: Milvus):
    orch = Orchestrator(db=db, nats=nats, milvus=milvus)
    try:
        await orch.stop(simulation_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to stop: {e}")
    return {"message": f"Simulation {simulation_id} stopped"}
