from pydantic_settings import BaseSettings
from dataclasses import dataclass
from typing import Dict, Literal
from autogen_core.models import ModelInfo


class OpenAISettings(BaseSettings):
    baseurl: str = ""
    apikey: str = ""


@dataclass
class ModelEntry:
    name: str
    info: ModelInfo


ModelName = Literal[
    "llama-3.1-8b-instruct",
    "llama-3.3-70b-instruct",  # free
    "gpt-4o-mini-2024-07-18",  # cheap
    "o4-mini-2025-04-16",  # more expensive
]


class AvailableModels:
    _models: Dict[str, ModelEntry] = {
        "meta-llama-3.1-8b-instruct": ModelEntry(
            name="meta-llama-3.1-8b-instruct",
            info=ModelInfo(
                vision=False,
                function_calling=False,
                json_output=True,
                family="llama",
            ),
        ),
        "llama-3.3-70b-instruct": ModelEntry(
            name="llama-3.3-70b-instruct",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family="llama",
            ),
        ),
        "gpt-4o-mini-2024-07-18": ModelEntry(
            name="gpt-4o-mini-2024-07-18",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family="gpt",
            ),
        ),
        "o4-mini-2025-04-16": ModelEntry(
            name="o4-mini-2025-04-16",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family="gpt",
            ),
        ),
    }

    @classmethod
    def get(cls, model: ModelName) -> ModelEntry:
        return cls._models[model]

    @classmethod
    def all(cls) -> Dict[str, ModelEntry]:
        return cls._models

    @classmethod
    def get_default(cls) -> ModelEntry:
        """
        Return the default model entry.
        """
        return cls._models["llama-3.3-70b-instruct"]
