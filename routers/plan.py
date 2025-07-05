from fastapi import APIRouter, HTTPException
from loguru import logger

from clients import Nats
from clients.sqlite import DB

from config.base import settings

from services.agent import AgentService
from services.plan import PlanService

from schemas.plan import Plan

router = APIRouter(prefix="/simulation/{simulation_id}/plan", tags=["Plan"])


@router.post("")
async def create_plan(
    simulation_id: str,
    nats: Nats,
    db: DB,
    owner: str,
    goal: str | None,
    participants: list[str] | None,
    tasks: list[str] | None,
):
    """Create a plan for the simulation"""
    try:
        plan = Plan(
            simulation_id=simulation_id,
            owner_id=owner,
            goal=goal,
        )
        db.add(plan)
        db.commit()
    except Exception as e:
        logger.error(f"Error creating plan: {e}")
        return {"message": "Error creating plan"}
    return {"message": "Plan created successfully!"}


@router.post("/{plan_id}/participant/{agent_id}/add")
async def add_participant(
    simulation_id: str,
    plan_id: str,
    db: DB,
    nats: Nats,
    agent_id: str,
):
    """Add a participant to a plan"""
    plan_service = PlanService(db=db, nats=nats)
    agent_service = AgentService(db=db, nats=nats)
    plan = plan_service.get_by_id(plan_id)
    agent = agent_service.get_by_id(agent_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.participating_in_plan_id is not None:
        raise HTTPException(
            status_code=400, detail="Agent is already participating in a plan"
        )

    agent.participating_in_plan_id = plan_id
    db.add(agent)
    db.commit()

    return {"message": "Participant added successfully"}


@router.delete("/{plan_id}/participant/{agent_id}/remove")
async def remove_participant(
    simulation_id: str,
    plan_id: str,
    db: DB,
    nats: Nats,
    agent_id: str,
):
    """Remove a participant from a plan"""
    agent_service = AgentService(db=db, nats=nats)
    agent = agent_service.get_by_id(agent_id)
    agent.participating_in_plan_id = None
    db.add(agent)
    db.commit()
    return {"message": "Participant removed successfully"}


# @router.get("/{plan_id}/tasks")
# async def get_tasks(plan_id: str, db: DB):
#     """Get all tasks in a plan"""
#     table = db.table(settings.tinydb.tables.task_table)
#     tasks = table.search(Query().plan_id == plan_id)
#     return tasks


@router.post("/{plan_id}/task/{task_id}/add")
async def add_task(
    simulation_id: str,
    plan_id: str,
    task_id: str,
    db: DB,
    nats: Nats,
    target: str,
    payoff: int,
):
    """Create and add a task to a plan"""

    try:
        plan = get_plan(db, nats, plan_id, simulation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plan not found")

    if task_id in plan.get_tasks():
        raise HTTPException(status_code=400, detail="Task already in plan")

    # create task
    try:
        task = Task(
            id=task_id, nats=nats, db=db, plan_id=plan_id, simulation_id=simulation_id
        )
        task.target = target  # resource.id
        task.payoff = payoff
        task.create()
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return {"message": "Error creating task"}

    return {"message": "Task added successfully"}


# @router.get("/{plan_id}/task/{task_id}")
# async def get_task_data(
#     simulation_id: str, plan_id: str, task_id: str, db: DB, nats: Nats
# ):
#     """Get a task by ID"""
#     try:
#         task = get_task(db, nats, task_id, plan_id, simulation_id)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     return task._get_task_dict()


@router.delete("/{plan_id}/task/{task_id}/remove")
async def remove_task(
    simulation_id: str, plan_id: str, task_id: str, db: DB, nats: Nats
):
    """Remove a task from a plan and delete from database"""
    try:
        plan = get_plan(db, nats, plan_id, simulation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plan not found")

    if task_id not in plan.get_tasks():
        raise HTTPException(status_code=404, detail="Task not found in plan")
    # delete task from database
    table = db.table(settings.tinydb.tables.task_table, cache_size=0)
    query = (Query().id == task_id) & (Query().plan_id == plan_id)
    table.remove(query)
    return {"message": "Task removed successfully"}


# @router.put("/{plan_id}/task/{task_id}/status")
# async def update_task_status(
#     simulation_id: str, plan_id: str, task_id: str, status: str, db: DB, nats: Nats
# ):
#     """Update the status of a task"""
#     try:
#         task = get_task(db, nats, task_id, simulation_id)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))

#     try:
#         new_status = TaskStatus(status)
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid task status")

#     task.update_status(new_status)
#     return {"message": "Task status updated successfully"}


@router.put("/{plan_id}/task/{task_id}/assign")
async def assign_task(
    simulation_id: str, plan_id: str, task_id: str, agent_id: str, db: DB, nats: Nats
):
    """Assign a task to an agent"""
    try:
        task = get_task(db, nats, task_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    task.assign_agent(agent_id)
    return {"message": "Task assigned successfully"}


# @router.get("/{plan_id}/task/{task_id}/target")
# async def get_task_target(
#     simulation_id: str, plan_id: str, task_id: str, db: DB, nats: Nats
# ):
#     """Get the target of a task"""
#     try:
#         task = get_task(db, nats, task_id, plan_id, simulation_id)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))

#     return {"target": task.get_target()}
