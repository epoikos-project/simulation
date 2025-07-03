from fastapi import APIRouter

from clients import Milvus
from clients.neo4j import Neo4j

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.get("/milvus/collections")
async def list_milvus_collections(milvus: Milvus):
    """List all collections in Milvus"""
    collections = milvus.list_collections()

    collections_with_stats = [
        {"name": collection, "stats": milvus.get_collection_stats(collection)}
        for collection in collections
    ]

    return collections_with_stats


@router.get("/n4o4j/connection/test")
async def test_n4o4j_connection(n4o4j: Neo4j):
    """Test connection to N4O4J"""
    # Assuming n4o4j has a method to check connection
    try:
        n4o4j.verify_connectivity()
        return {"status": "Connection successful"}
    except Exception as e:
        return {"status": "Connection failed", "error": str(e)}
