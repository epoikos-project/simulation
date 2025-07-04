from engine.context import Context


class MemoryContext(Context):
    def build(self, memory: str) -> str:
        if memory:
            memory_description = "Memory: You have the following memory: " + memory
        else:
            memory_description = "Memory: You do not have any memory about past observations and events. "
        return memory_description
