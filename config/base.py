from pydantic_settings import BaseSettings, SettingsConfigDict

from config.openai import OpenAISettings
from config.tinydb import TinyDBSettings
from config.milvus import MilvusSettings
from config.nats import NatsSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # use double underscore for nested settings; single-underscore envs will be top-level and ignored
        env_nested_delimiter="__",
        extra="ignore",
    )
    nats: NatsSettings = NatsSettings()
    tinydb: TinyDBSettings = TinyDBSettings()
    milvus: MilvusSettings = MilvusSettings()
    openai: OpenAISettings = OpenAISettings()
    # Feature flag: enable cluster-based asynchronous optimization
    cluster_optimization: bool = True


settings = Settings()
