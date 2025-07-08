from engine.context.base import BaseContext

from schemas.action_log import ActionLog
from schemas.agent import Agent
from schemas.memory_log import MemoryLog


class MemoryContext(BaseContext):
    def build(self, **kwargs) -> str:
        actions: list[ActionLog] = kwargs.get("actions", [])
        memory_logs: list[MemoryLog] = kwargs.get("memory_logs", [])

        # remove 'update_plan' actions from the list
        actions = [
            action for action in actions if not action.action.startswith("update_plan(")
        ]

        action_log = "\n".join(
            [
                f" - {action.action} {'Feedback: ' + action.feedback if action.feedback else 'Succeeded'} (Tick: {action.tick})"
                for action in actions
            ]
        )

        memory_log = "\n".join(
            [
                f" - {memory.memory} (Tick: {memory.tick})"
                + (
                    " (You will lose this oldest plan entry in the next tick. If the information is still needed, include it in your update of the plan.)"
                    if idx == len(memory_logs) - 1
                    else ""
                )
                for idx, memory in enumerate(memory_logs)
            ]
        )

        # if memory_log == "":
        #     memory_log = (
        #         "You have not added any memories yet. Consider doing so to plan ahead."
        #     )

        memory_description = (
            "Memory: Previously you have performed the following actions: \n"
            + action_log
            + "\n---\nPlan: These are your last 3 planning steps, you saved to perform informed future actions:\n"
            + memory_log
            + "\n---"
        )

        return memory_description
