from pydantic import BaseModel

class SimulationCreatedMessage(BaseModel):
    id: str
    config_name: str

    def get_channel_name(self) -> str:
        return f"simulation.{self.id}.created"