from clients.nats import nats_broker
from clients.tinydb import get_client
from models.context import (
    Message,
    Observation,
    PlanContext,
    TaskContext,
)
from models.plan import get_plan
from models.task import get_task

SYSTEM_MESSAGE = (
    "You are a person living in an environment with other people. Your main goal is to survive in this environment by consuming resources in order to increase your energy level. "
    "Your energy level is reduced over time with every action you take. In order to survive you NEED to: "
    "(1) explore the environment to discover (new) resources, "
    "(2) harvest resources by forming plans and executing them and "
    "(3) talk and cooperate with other agents to execute more favorable plans and collect more resources. "
    "\nTo guide your actions, you should use the information about your environment and talk to other people that are around."
)
DESCRIPTION = "These are your personal attributes: ID: {id}, Name: {name}, Current location: {location}"  # , Personality: {personality}. "


class HungerContextPrompt:
    def build(self, energy_level: int, hunger: int) -> str:
        if energy_level <= hunger:
            hunger_description = f"Energy level: Your current energy level is {energy_level}. You are starving and need to find and consume resources immediately. "
        else:
            hunger_description = f"Energy level: Your current energy level is {energy_level}. You are not starving, but you should consume resources to maintain your energy level. "
        return (
            hunger_description
            + f"Otherwise you will die after {energy_level} actions. "
        )


class ObservationContextPrompt:
    def build(self, observations: list[Observation]) -> str:
        observation_description = (
            "Observations: You have made the following observations in your surroundings: "
            + ", ".join([str(obs) for obs in observations])
            if observations
            else "Observations: You have not made any observations yet. Move around to discover your surroundings. "
        )
        return observation_description


class PlanContextPrompt:
    def __init__(self):
        self.db = get_client()
        self.nats = nats_broker()

    def build(
        self,
        plan_ownership: str | None,
        plan_participation: list,
        assigned_tasks: list,
        simulation_id: str,
    ) -> str:
        # ownership
        if plan_ownership:
            plan_obj = get_plan(self.db, self.nats, plan_ownership, simulation_id)
            plan_ownership_context = "You are the owner of the following plan: "
            plan_context = PlanContext(
                id=plan_obj.id,
                owner=plan_obj.owner if plan_obj.owner else "",
                goal=plan_obj.goal if plan_obj.goal else "",
                participants=plan_obj.get_participants(),
                tasks=plan_obj.get_tasks(),
                total_payoff=plan_obj.total_payoff,
            )
            plan_ownership_context += str(plan_context) + " "

            tasks_obj = [
                get_task(self.db, self.nats, task_id, simulation_id)
                for task_id in plan_obj.get_tasks()
            ]
            if tasks_obj:
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
                plan_ownership_context += (
                    "These are the current tasks associated with this plan: "
                    + ", ".join(map(str, tasks_context))
                )
            else:
                plan_ownership_context += (
                    "This plan has no tasks associated with it. Add tasks to it! "
                )
        else:
            plan_ownership_context = "You do not own any plans. "

        # participation
        if plan_participation and not (plan_participation == [plan_ownership]):
            plan_participation_context = (
                "You are participating in the following plans owned by other people: "
            )
            for plan_id in plan_participation:
                if plan_id == plan_ownership:
                    continue
                plan_obj = get_plan(self.db, self.nats, plan_id, simulation_id)
                plan_context = PlanContext(
                    id=plan_obj.id,
                    owner=plan_obj.owner if plan_obj.owner else "",
                    goal=plan_obj.goal if plan_obj.goal else "",
                    participants=plan_obj.get_participants(),
                    tasks=plan_obj.get_tasks(),
                    total_payoff=plan_obj.total_payoff,
                )
                plan_participation_context += str(plan_context) + " "

                tasks_obj = [
                    get_task(self.db, self.nats, task_id, simulation_id)
                    for task_id in plan_obj.get_tasks()
                ]
                if tasks_obj:
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
                    plan_participation_context += (
                        "These are the current tasks associated with this plan: "
                        + ", ".join(map(str, tasks_context))
                    )
                else:
                    plan_participation_context += "This plan has no tasks associated with it. Wait for the owner to add tasks. "

        else:
            plan_participation_context = (
                "You are not participating in any plans owned by other people. "
            )
            if not plan_ownership:
                plan_participation_context += "As you also do not own any plans, consider to either former a new plan or join an existing one. "

        # assigned tasks
        if assigned_tasks:
            assigned_tasks_context = (
                "You are responsible to execute the following tasks: "
            )
            for task_id in assigned_tasks:
                task_obj = get_task(self.db, self.nats, task_id, simulation_id)
                task_context = TaskContext(
                    id=task_obj.id,
                    plan_id=task_obj.plan_id,
                    target=task_obj.target,
                    payoff=task_obj.payoff,
                    # status=task_obj.status,
                    worker=task_obj.worker,
                )
                assigned_tasks_context += str(task_context) + " "
        else:
            assigned_tasks_context = "You are not responsible to execute any task. Consider taking on responsibility for available tasks. "

        plans_description = (
            "Plans: "
            + plan_ownership_context
            + "\n"
            + plan_participation_context
            + "\n"
            + assigned_tasks_context
        )

        # TODO: ensure this by adaptive tool calls and improved prompting
        # has_plan = "You ALREADY HAVE a plan." if plan_id else "You do not have a plan"
        # has_three_tasks = (
        #     "YOU ALREADY HAVE 3 tasks."
        #     if plan_obj and len(plan_obj.get_tasks()) >= 3
        #     else "You do not have 3 tasks."
        # )

        # plan_restrictions = (
        #     f"IMPORTANT: You can ONLY HAVE ONE PLAN {has_plan}.\n "
        #     + f"If you have a plan always add at least one task, at most 3. {has_three_tasks} \n "
        #     + "Once you have a plan and tasks, start moving towards the target of the task. \n"
        # )

        return plans_description


class ConversationContextPrompt:
    def build(self, message: Message, conversation_id: str | None) -> str:
        if conversation_id:
            conversation_context = (
                f"You are currently engaged in a conversation (ID: {conversation_id}). "
            )
            conversation_context += f"New message from person {message.sender_id}: <Message start> {message.content} <Message end> "
            conversation_context += "If appropriate consider replying. If you do not reply the conversation will be terminated. "

        else:
            conversation_context = "You are currently not engaged in a conversation with another person. If you meet someone, consider starting a conversation. "

        # TODO: add termination logic or reconsider how this should work. Consider how message history is handled.
        # Should not overflow the context. Maybe have summary of conversation and newest message.
        # Then if decide to reply this is handled by other agent (MessageAgent) that gets the entire history and sends the message.
        # While this MessageAgent would also need quite the same context as here, its task would only be the reply and not deciding on a tool call.

        conversation_description = "Conversation: " + conversation_context

        return conversation_description


class MemoryContextPrompt:
    def build(self, memory: str) -> str:
        if memory:
            memory_description = f"Memory: {memory}\n"
        else:
            memory_description = (
                "Memory: You do not have any memory about past observations and events. "
                + "\n"
            )
        return memory_description
