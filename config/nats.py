from pydantic_settings import BaseSettings


class NatsSettings(BaseSettings):
    url: str = ""
