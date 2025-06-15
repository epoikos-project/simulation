from pydantic_settings import BaseSettings, SettingsConfigDict
from dataclasses import dataclass
from typing import Dict, Literal
from autogen_core.models import ModelInfo


class OpenAISettings(BaseSettings):
    # use double underscore for nested vars; ignore any other OPENAI_* envs
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )
    baseurl: str = ""
    apikey: str = ""


@dataclass
class ModelEntry:
    name: str
    info: ModelInfo

ModelName = Literal[
        "llama-3.1-8b-instruct",
        "llama-3.3-70b-instruct",
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
        ),
        "llama-3.3-70b-instruct": ModelEntry(
            name="llama-3.3-70b-instruct",
            info=ModelInfo(
                vision=False,
                function_calling=True,
                json_output=True,
                family="UNKNOWN",
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
