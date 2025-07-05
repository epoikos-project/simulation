from fastapi import APIRouter

from clients import Milvus

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
