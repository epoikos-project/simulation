from pydantic_settings import BaseSettings, SettingsConfigDict
from config.nats import NatsSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_nested_delimiter="_"
    )
    nats: NatsSettings = NatsSettings()


settings = Settings()
