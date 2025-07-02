from pydantic_settings import BaseSettings


class Neo4jSettings(BaseSettings):
    uri: str = ""
    username: str = ""
    password: str = ""
