from sqlmodel import Field, SQLModel

from schemas.base import BaseModel


class Configuration(BaseModel, table=True):
    name: str = Field()
    agents: str = Field()
    settings: str = Field()
