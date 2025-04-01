from pydantic_settings import BaseSettings, SettingsConfigDict

from config.tinydb import TinyDBSettings
from config.milvus import MilvusSettings
from config.nats import NatsSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="_",
        extra="ignore",
    )
    nats: NatsSettings = NatsSettings()
    tinydb: TinyDBSettings = TinyDBSettings()
    milvus: MilvusSettings = MilvusSettings()


settings = Settings()
