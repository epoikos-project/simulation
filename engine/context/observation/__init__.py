from typing import Annotated, Union

from pydantic import Field
from .agent import AgentObservation
from .resource import ResourceObservation
from .other import OtherObservation
from .base import BaseObservation

Observation = Annotated[
    Union[ResourceObservation, AgentObservation, OtherObservation],
    Field(discriminator="type"),
]

__all__ = [
    "AgentObservation",
    "ResourceObservation",
    "OtherObservation",
    "BaseObservation",
    "Observation",
]
