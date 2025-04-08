from pydantic_settings import BaseSettings


class TableSettings(BaseSettings):
    agent_table: str = "agents"
    simulation_table: str = "simulations"
    world: str = "world"


class TinyDBSettings(BaseSettings):
    path: str = ""
    tables: TableSettings = TableSettings()
