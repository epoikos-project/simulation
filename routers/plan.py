from fastapi import APIRouter, HTTPException
from loguru import logger
from clients import Nats, DB
from models.plan import Plan
from config.base import settings
from tinydb import Query
from models.plan import get_plan
from models.task import Task, TaskStatus, get_task

# TODO: add NATS stream

router = APIRouter(prefix="/simulation/{simulation_id}/plan", tags=["Plan"])


@router.post("")
async def create_plan(
    simulation_id: str,
    plan_id: str,
    nats: Nats,
    db: DB,
    owner: str,
    goal: str | None,
    participants: list[str] | None,
    tasks: list[str] | None,
):
    """Create a plan for the simulation"""
    try:
        plan = Plan(db=db, id=plan_id, nats=nats, simulation_id=simulation_id)
        plan.owner = owner
        plan.participants = participants or []
        plan.goal = goal
        # TODO: validate if owner, participants, and tasks exist in the simulation?

        plan.create()
    except Exception as e:
        logger.error(f"Error creating plan: {e}")
        return {"message": "Error creating plan"}
    return {"message": "Plan created successfully!"}


@router.get("/{plan_id}")
async def get_plan_data(simulation_id: str, plan_id: str, db: DB, nats: Nats):
    """Get a plan by ID"""
    try:
        plan = get_plan(db, nats, plan_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return plan._get_plan_dict()


@router.get("")
async def list_plans(simulation_id: str, db: DB):
    """List all plans in the simulation"""
    table = db.table(settings.tinydb.tables.plan_table)
    plans = table.search(Query().simulation_id == simulation_id)
    return plans


@router.delete("/{plan_id}")
async def delete_plan(simulation_id: str, plan_id: str, db: DB):
    """Delete a plan by ID"""
    table = db.table(settings.tinydb.tables.plan_table)
    query = (Query().id == plan_id) & (Query().simulation_id == simulation_id)
    plan = table.get(query)
    if plan is None:
        return {"message": "Plan not found"}
    table.remove(query)
    return {"message": "Plan deleted successfully!"}


@router.post("/{plan_id}/participant/{agent_id}/add")
async def add_participant(
    simulation_id: str,
    plan_id: str,
    db: DB,
    nats: Nats,
    agent_id: str,
):
    """Add a participant to a plan"""
    try:
        plan = get_plan(db, nats, plan_id, simulation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plan not found")

    if agent_id in plan.participants:
        raise HTTPException(status_code=400, detail="Participant already in plan")

    # add participant to plan
    plan.add_participant(agent_id)
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
    try:
        plan = get_plan(db, nats, plan_id, simulation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plan not found")

    if agent_id not in plan.participants:
        raise HTTPException(status_code=400, detail="Participant not in plan")

    # remove participant from plan
    plan.remove_participant(agent_id)
    return {"message": "Participant removed successfully"}


# TODO: should task related endpoints have a separate router?
# If tasks can not exist without a plan (which I would argue), then it might make sense to have them here.
# Otherwise they could exist independently.


@router.get("/{plan_id}/tasks")
async def get_tasks(plan_id: str, db: DB):
    """Get all tasks in a plan"""
    table = db.table(settings.tinydb.tables.task_table)
    tasks = table.search(Query().plan_id == plan_id)
    return tasks


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


@router.get("/{plan_id}/task/{task_id}")
async def get_task_data(
    simulation_id: str, plan_id: str, task_id: str, db: DB, nats: Nats
):
    """Get a task by ID"""
    try:
        task = get_task(db, nats, task_id, plan_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return task._get_task_dict()  # TODO: return dict or object?


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
    table = db.table(settings.tinydb.tables.task_table)
    query = (Query().id == task_id) & (Query().plan_id == plan_id)
    table.remove(query)
    return {"message": "Task removed successfully"}


@router.put("/{plan_id}/task/{task_id}/status")
async def update_task_status(
    simulation_id: str, plan_id: str, task_id: str, status: str, db: DB, nats: Nats
):
    """Update the status of a task"""
    try:
        task = get_task(db, nats, task_id, plan_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        new_status = TaskStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task status")

    task.update_status(new_status)
    return {"message": "Task status updated successfully"}


@router.put("/{plan_id}/task/{task_id}/assign")
async def assign_task(
    simulation_id: str, plan_id: str, task_id: str, agent_id: str, db: DB, nats: Nats
):
    """Assign a task to an agent"""
    try:
        task = get_task(db, nats, task_id, plan_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    task.assign_agent(agent_id)
    return {"message": "Task assigned successfully"}


@router.get("/{plan_id}/task/{task_id}/target")
async def get_task_target(
    simulation_id: str, plan_id: str, task_id: str, db: DB, nats: Nats
):
    """Get the target of a task"""
    try:
        task = get_task(db, nats, task_id, plan_id, simulation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"target": task.get_target()}
