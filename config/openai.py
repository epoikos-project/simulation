from dataclasses import dataclass
from typing import Dict, Literal

from autogen_core.models import ModelFamily, ModelInfo
from pydantic_settings import BaseSettings


class OpenAISettings(BaseSettings):
    baseurl: str = ""
    apikey: str = ""


@dataclass
class ModelEntry:
    name: str
    info: ModelInfo
    reasoning: bool = True


ModelName = Literal[
    "llama-3.1-8b-instruct",
    "llama-3.3-70b-instruct",
    "gpt-4o-mini-2024-07-18",
    "o4-mini-2025-04-16",
    "gpt-4.1-nano-2025-04-14",
]


class AvailableModels:
    _models: Dict[str, ModelEntry] = {
        "meta-llama-3.1-8b-instruct": ModelEntry(
            name="meta-llama-3.1-8b-instruct",
            info=ModelInfo(
                vision=False,
                function_calling=False,
                json_output=True,
                family="UNKNOWN",
            ),
            reasoning=False,
        ),
        "llama-3.3-70b-instruct": ModelEntry(
            name="llama-3.3-70b-instruct",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family="UNKNOWN",
            ),
            reasoning=False,
        ),
        "gpt-4o-mini-2024-07-18": ModelEntry(
            name="gpt-4o-mini-2024-07-18",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family=ModelFamily.GPT_4O,
            ),
            reasoning=False,
        ),
        "o4-mini-2025-04-16": ModelEntry(
            name="o4-mini-2025-04-16",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family=ModelFamily.O3,
            ),
            reasoning=True,
        ),
        "gpt-4.1-nano-2025-04-14": ModelEntry(
            name="gpt-4.1-nano-2025-04-14",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family=ModelFamily.GPT_4,
            ),
            reasoning=False,
        ),
    }

    @classmethod
    def get(cls, model: ModelName) -> ModelEntry:
        return cls._models[model]

    @classmethod
    def all(cls) -> Dict[str, ModelEntry]:
        return cls._models

    @classmethod
    def list(cls) -> list[str]:
        """
        Return a list of all model names.
        """
        return [{**{"id": key}, **vars(entry)} for key, entry in cls._models.items()]

    @classmethod
    def get_default(cls) -> ModelEntry:
        """
        Return the default model entry.
        """
        return cls._models["llama-3.3-70b-instruct"]
