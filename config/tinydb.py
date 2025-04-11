from pydantic_settings import BaseSettings


class TableSettings(BaseSettings):
    agent_table: str = "agents"
    simulation_table: str = "simulations"
    world: str = "world"
    region: str = "regions"
    resource: str = "resources"


class TinyDBSettings(BaseSettings):
    path: str = ""
    tables: TableSettings = TableSettings()
