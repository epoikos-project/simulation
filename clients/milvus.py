import os
from typing import Annotated

from fastapi.params import Depends
from pymilvus import MilvusClient

from config import settings


def create_client():
    os.makedirs("/".join(settings.milvus.path.split("/")[:-1]), exist_ok=True)
    return MilvusClient(settings.milvus.path)


def get_client():
    yield MilvusClient(settings.milvus.path)


Milvus = Annotated[MilvusClient, Depends(get_client)]
