import json

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlmodel import Session, select

from clients.db import DB
from config.openai import AvailableModels
from schemas.configuration import Configuration

router = APIRouter(prefix="/configuration", tags=["Configuration"])


@router.get("/models")
async def get_available_models():
    """
    Get a list of available models for the orchestrator.
    This is a placeholder function that should be implemented to return actual model data.
    """
    return AvailableModels.list()


@router.post("")
async def save_configuration(
    config: Configuration,
    db: DB,
):
    """
    Save or update a configuration based on its name in Postgres.
    """
    stmt = select(Configuration).where(Configuration.name == config.name)
    existing = db.exec(stmt).one_or_none()
    try:
        if existing:
            existing.agents = json.dumps(config.agents)
            existing.settings = json.dumps(config.settings)
            db.add(existing)
        else:
            new_conf = Configuration(
                name=config.name,
                agents=json.dumps(config.agents),
                settings=json.dumps(config.settings),
            )
            # initialize last_used to created_at for new configuration
            new_conf.last_used = new_conf.created_at
            db.add(new_conf)
            existing = new_conf
        db.commit()
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        raise HTTPException(status_code=500, detail="Error saving configuration")
    return {
        "message": f"Configuration '{existing.name}' saved successfully!",
        "id": existing.id,
    }


@router.get("/{name}")
async def get_configuration(
    name: str,
    db: DB,
):
    """
    Retrieve a specific configuration by its name.
    """
    stmt = select(Configuration).where(Configuration.name == name)
    existing = db.exec(stmt).one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {
        "id": existing.id,
        "name": existing.name,
        "agents": json.loads(existing.agents),
        "settings": json.loads(existing.settings),
        "created_at": existing.created_at,
        "last_used": existing.last_used,
    }


@router.get("/")
async def get_all_configurations(
    db: DB,
):
    """
    Retrieve all configurations.
    """
    results = []
    for conf in db.exec(select(Configuration)).all():
        results.append({
            "id": conf.id,
            "name": conf.name,
            "agents": json.loads(conf.agents),
            "settings": json.loads(conf.settings),
            "created_at": conf.created_at,
            "last_used": conf.last_used,
        })
    return results


@router.delete("/{name}")
async def delete_configuration(
    name: str,
    db: DB,
):
    """
    Delete a configuration by its name.
    """
    stmt = select(Configuration).where(Configuration.name == name)
    existing = db.exec(stmt).one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration not found")
    db.delete(existing)
    db.commit()
    return {"message": f"Configuration '{name}' deleted successfully!"}
