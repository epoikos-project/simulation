from pydantic import BaseModel, Field
from enum import Enum
from typing import Annotated, Union, Literal

# from typing import Optional


class ObservationType(str, Enum):
    RESOURCE = "Resource"
    AGENT = "Agent"
    OBSTACLE = "Obstacle"
    ERROR = "Execution_Error"
    OTHER = "Other"
