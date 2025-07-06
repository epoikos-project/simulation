import uuid
from typing import Annotated

from langfuse.decorators import observe
from loguru import logger

from clients.db import get_session

from schemas.plan import Plan
from schemas.task import Task

# from fastapi import HTTPException


# Use `Annotated` to describe each function parameter for the LLM.
# The `agent_id` and `simulation_id` arguments are automatically injected by the agent at runtime and never exposed to the LLM.
# This is done to reduce the amount of information the LLM needs to generate and thereby keep the tool calls simple.
# Make sure to always include the `agent_id` and `simulation_id` arguments in your function signature even if you don't use them in the function body.
# If there is need to inject more arguments, we can consider to further refactor the code.
@observe()
async def make_plan(
    goal: Annotated[
        str,
        "A concise description of the goal of the plan.",
    ],
    # participants: Annotated[
    #     list[Annotated[str, "The agents that are participating in the plan."]],
    #     "A list of participants",
    # ], # Participants will join the plan by separate tool call
    # tasks: Annotated[
    #     list[Annotated[str, "A short description of the task"]],
    #     "A list of tasks that have to be performed to execute the plan.",
    # ], # Tasks will be added by separate tool call
    agent_id: str,
    simulation_id: str,
):
    """Form a new plan for resource acquisition. You can only ever have one plan at a time."""

    from clients.db import get_session
    from clients.nats import nats_broker

    logger.success("Calling tool make_plan")

    with get_session() as db:
        nats = nats_broker()

        try:

            plan = Plan(owner_id=agent_id, simulation_id=simulation_id, goal=goal)

            db.add(plan)
            db.commit()

        except Exception as e:
            logger.error(f"Error creating plan: {e}")
            raise e


@observe()
async def add_task(
    target: Annotated[str, "The ID of the resource to be acquired by the task."],
    payoff: Annotated[int, "The expected payoff of the task."],
    plan_id: Annotated[str, "The ID of the plan to which the task will be added."],
    agent_id: str,
    simulation_id: str,
):
    """Create a new task for resource collection and add this task to a plan."""

    logger.success("Calling tool add_task")

    with get_session() as db:

        # TODO: check how error handling effects autogen tool calls
        # try:
        #     plan = get_plan(db, nats, plan_id, simulation_id)
        # except ValueError:
        #     raise HTTPException(status_code=404, detail="Plan not found")

        # if task_id in plan.get_tasks():
        #     raise HTTPException(status_code=400, detail="Task already in plan")

        try:
            task = Task(
                simulation_id=simulation_id,
                target_id=target,  # resource.id
                payoff=payoff,
            )
            db.add(task)
            db.commit()
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise e


# @observe()
# async def take_on_task(
#     task_id: Annotated[str, "The ID of the task to you will work on."],
#     agent_id: str,
#     simulation_id: str,
# ):
#     """Take responsibility for a task and join its plan."""
#     from clients.tinydb import get_client
#     from clients.nats import nats_broker

#     logger.success("Calling tool take_on_task")

#     db = get_client()
#     nats = nats_broker()

#     try:
#         task = get_task(db, nats, task_id, simulation_id)
#         plan_id = task.plan_id
#         plan = get_plan(db, nats, plan_id, simulation_id)
#     except ValueError as e:
#         logger.error(f"Error getting task: {e}")
#         raise e
#         # raise HTTPException(status_code=404, detail=str(e))

#     plan.add_participant(agent_id)
#     task.assign_agent(agent_id)
