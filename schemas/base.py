import uuid
from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex[:6])
