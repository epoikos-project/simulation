# Third Party
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.db import DBSettings
from config.milvus import MilvusSettings
from config.nats import NatsSettings
from config.openai import OpenAISettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="_",
        extra="ignore",
    )
    nats: NatsSettings = NatsSettings()
    milvus: MilvusSettings = MilvusSettings()
    openai: OpenAISettings = OpenAISettings()
    db: DBSettings = DBSettings()


settings = Settings()
