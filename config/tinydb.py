from pydantic_settings import BaseSettings


class TableSettings(BaseSettings):
    agent_table: str = "agents"
    simulation_table: str = "simulations"
    world_table: str = "world"
    region_table: str = "regions"
    resource_table: str = "resources"
    configuration_table: str = "configurations"
    plan_table: str = "plans"
    task_table: str = "tasks"
    agent_conversation_table: str = "agent_conversations"


class TinyDBSettings(BaseSettings):
    path: str = ""
    tables: TableSettings = TableSettings()
