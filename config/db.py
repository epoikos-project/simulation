from pydantic_settings import BaseSettings


class DBSettings(BaseSettings):
    url: str = ""
