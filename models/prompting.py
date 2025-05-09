from models.plan import get_plan
from models.task import get_task
from models.context import (
    Observation,
    # AgentObservation,
    # ResourceObservation,
    # ObstacleObservation,
    # OtherObservation,
    Message,
    # ObservationType,
    PlanContext,
    TaskContext,
)
from clients.tinydb import get_client
from clients.nats import nats_broker


SYSTEM_MESSAGE = (
    "You are a person living in an environment with other people. Your main goal is to survive in this environment by consuming resources in order to increase your energy level. "
    "Your energy level is reduced for every action you take. In order to survive you NEED to: "
    "(1) explore the environment to discover (new) resources, "
    "(2) harvest resources by forming plans and executing them and "
    "(3) talk and cooperate with other agents to execute more favourable plans and collect more resources. "
    "\nTo guide your actions, you should use the information about your environment and talk to other people that are around. If you just meet them and this is a new conversation, start a conversation. Else if it is ongoing engage in that conversation. "
    "You can only move one coordinate at a time and for moving you have to choose a location different to your current location."
)
DESCRIPTION = "These are your personal attributes: Agent ID: {id}, Name: {name}"  # , Personality: {personality}. "


class HungerContextPrompt:
    def build(self, hunger: int) -> str:
        hunger_description = f"Your current hunger level is {hunger}.  "
        return hunger_description


class ObservationContextPrompt:
    def build(self, observations: list[Observation]) -> str:
        observation_description = (
            "You have made the following observations in your surroundings: "
            + "; ".join([str(obs) for obs in observations])
            if observations
            else "You have not made any observations yet. "
        )
        return (
            observation_description
            + "\n"
            + "If you are close to an agent, engage in conversation with them. \n"
        )


class PlanContextPrompt:
    def __init__(self):
        self.db = get_client()
        self.nats = nats_broker()

    def build(self, plan_id: str, simulation_id: str) -> str:
        plan_obj = (
            get_plan(self.db, self.nats, plan_id, simulation_id) if plan_id else None
        )
        plan_context = (
            PlanContext(
                id=plan_obj.id,
                owner=plan_obj.owner if plan_obj.owner else "",
                goal=plan_obj.goal if plan_obj.goal else "",
                participants=plan_obj.get_participants(),
                tasks=plan_obj.get_tasks(),
                total_payoff=plan_obj.total_payoff,
            )
            if plan_obj
            else None
        )

        if plan_obj:
            tasks_obj = [
                get_task(self.db, self.nats, task_id, simulation_id)
                for task_id in plan_obj.get_tasks()
            ]
        else:
            tasks_obj = []
        tasks_context = [
            TaskContext(
                id=task.id,
                plan_id=task.plan_id,
                target=task.target,
                payoff=task.payoff,
                # status=task.status,
                worker=task.worker,
            )
            for task in tasks_obj
        ]

        plans_description = (
            f"You are the owner of the following plan: {plan_context}. "
            f"These are the tasks in detail: "
            + ", ".join(map(str, tasks_context))
            + (
                "\n You have 0 tasks in your plan, it might make sense to add tasks using the add_task tool."
                if not tasks_context
                else ""
            )
            if plan_context
            else "You do not own any plans. "
        )

        # TODO
        # participating_plans_description = (
        #     "You are currently participating in the following plans: "
        #     + "; ".join(self.participating_plans)
        #     + "As part of these plans you are assigned to the following tasks: "
        #     + ", ".join(self.assigned_tasks)
        #     if self.participating_plans
        #     else "You are not currently participating in any plans and are not assigned to any tasks. "
        # )

        has_plan = "You ALREADY HAVE a plan." if plan_id else "You do not have a plan"
        has_three_tasks = (
            "YOU ALREADY HAVE 3 tasks."
            if plan_obj and len(plan_obj.get_tasks()) >= 3
            else "You do not have 3 tasks."
        )

        plan_restrictions = (
            f"IMPORTANT: You can ONLY HAVE ONE PLAN {has_plan}.\n "
            + f"If you have a plan always add at least one task, at most 3. {has_three_tasks} \n "
            + "Once you have a plan and tasks, start moving towards the target of the task. \n"
        )

        return plans_description + "\n" + plan_restrictions


class ConversationContextPrompt:
    def build(self, message: Message, conversation_id: str | None) -> str:
        conversation_observation = (
            f"You are currently engaged in a conversation with another agent with ID: {conversation_id}. "
            if conversation_id
            else ""
        )

        message_description = (
            f"There is a new message from: {message.sender_id}. If appropriate consider replying. If you do not reply the conversation will be terminated. <Message start> {message.content} <Message end> "
            if message.content
            else "There are no current messages from other people. "
        )  # TODO: add termination logic or reconsider how this should work. Consider how message history is handled.
        # Should not overflow the context. Maybe have summary of conversation and newest message.
        # Then if decide to reply this is handled by other agent (MessageAgent) that gets the entire history and sends the message.
        # While this MessageAgent would also need quite the same context as here, its task would only be the reply and not deciding on a tool call.
        return conversation_observation + "\n" + message_description


class MemoryContextPrompt:
    def build(self, memory: str) -> str:
        memory_description = (
            "You have the following memory: " + memory
            if memory
            else "You do not have any memory about past observations and events. "
        )  # TODO: either pass this in prompt here or use autogen memory field
        return memory_description
