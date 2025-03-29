import os
from typing import Annotated

from fastapi.params import Depends
from pymilvus import MilvusClient
from tinydb import TinyDB

from config import settings


def create_client():
    os.makedirs("/".join(settings.tinydb.path.split("/")[:-1]), exist_ok=True)
    if not os.path.exists(settings.tinydb.path):
        with open(settings.tinydb.path, "w"):
            pass
    return TinyDB(settings.tinydb.path)


def get_client():
    return TinyDB(settings.tinydb.path)


DB = Annotated[TinyDB, Depends(get_client)]
