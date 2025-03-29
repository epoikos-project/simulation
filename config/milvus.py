from pydantic_settings import BaseSettings


class MilvusSettings(BaseSettings):
    path: str = ""
