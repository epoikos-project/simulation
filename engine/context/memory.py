from engine.context.base import BaseContext
from schemas.action_log import ActionLog
from schemas.agent import Agent


class MemoryContext(BaseContext):
    def build(self, actions: list[ActionLog]) -> str:

        memory = "\n".join([f" - {action.action} (Tick: {action.tick})" for action in actions])
        memory_description = "Memory: You have the following memory: " + memory
       
        return memory_description
