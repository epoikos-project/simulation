from typing_extensions import Annotated
from fastapi.params import Depends
from neo4j import GraphDatabase

from config import settings

# URI examples: "neo4j://localhost", "neo4j+s://xxx.databases.neo4j.io"
URI = settings.neo4j.uri
AUTH = (settings.neo4j.username, settings.neo4j.password)

def get_driver():
    return GraphDatabase.driver(URI, auth=AUTH)

Neo4j = Annotated[GraphDatabase, Depends(get_driver)]
