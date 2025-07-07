from engine.context.base import BaseContext

from schemas.action_log import ActionLog
from schemas.agent import Agent
from schemas.memory_log import MemoryLog


class MemoryContext(BaseContext):
    def build(self, **kwargs) -> str:
        actions: list[ActionLog] = kwargs.get("actions", [])
        memory_logs: list[MemoryLog] = kwargs.get("memory_logs", [])

        action_log = "\n".join(
            [f" - {action.action} (Tick: {action.tick})" for action in actions]
        )

        memory_log = "\n".join(
            [
                f" - {memory.memory} (Tick: {memory.tick})"
                + (
                    " (You will lose this memory entry in the next tick. "
                    "If the information is still needed add it to your memory again)"
                    if idx == len(memory_logs) - 1
                    else ""
                )
                for idx, memory in enumerate(memory_logs)
            ]
        )

        if memory_log == "":
            memory_log = (
                "You have not added any memories yet. Consider doing so to plan ahead."
            )

        memory_description = (
            "Memory: Previously you have performed the following actions: \n"
            + action_log
            + "\nThese are the last 3 memories you saved to perform informed future actions:\n"
            + memory_log
        )

        return memory_description
