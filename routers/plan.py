# import asyncio

from fastapi import APIRouter
from loguru import logger

# from tinydb import Query
from clients import Nats, Milvus, DB
from models.plan import Plan

router = APIRouter(prefix="/simulation/{simulation_id}/plan", tags=["Plan"])


@router.post("")
async def create_plan(simulation_id: str, broker: Nats, db: DB, milvus: Milvus):
    """Create a plan for the simulation"""
    try:
        plan = Plan(db=db, id=simulation_id, nats=broker)
        await plan.create()
    except Exception as e:
        logger.error(f"Error creating plan: {e}")
        return {"message": "Error creating plan"}
    return {"message": "Plan created successfully!"}


@router.get("/{id}")
async def get_plan(id: str, simulation_id: str, db: DB):
    """Get a plan by ID"""
    pass


@router.get("")
async def list_plans(simulation_id: str, db: DB):
    """List all plans in the simulation"""
    pass


@router.delete("/{id}")
async def delete_plan(id: str, simulation_id: str, db: DB):
    """Delete a plan by ID"""
    pass
