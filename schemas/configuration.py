from sqlmodel import Field

from schemas.base import BaseModel
from typing import Optional

class Configuration(BaseModel, table=True):
    name: str = Field()
    agents: str = Field()
    settings: str = Field()
    last_used: Optional[str] = Field(default=None, nullable=True)
