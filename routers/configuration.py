from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from tinydb import TinyDB
from models.configuration import Configuration, ConfigurationData
from clients.tinydb import get_client

router = APIRouter(prefix="/configuration", tags=["Configuration"])

@router.post("")
async def save_configuration(
    config: ConfigurationData,
    db: TinyDB = Depends(get_client)
):
    """
    Save or update a configuration based on its name.
    """
    config_model = Configuration(db)
    try:
        config_model.save(config.dict())
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        raise HTTPException(status_code=500, detail="Error saving configuration")
    return {"message": f"Configuration '{config.name}' saved successfully!", "id": config.id}

@router.get("/{name}")
async def get_configuration(
    name: str,
    db: TinyDB = Depends(get_client)
):
    """
    Retrieve a specific configuration by its name.
    """
    config_model = Configuration(db)
    config_data = config_model.get(name)
    if config_data is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return config_data

@router.get("/")
async def get_all_configurations(
    db: TinyDB = Depends(get_client)
):
    """
    Retrieve all available configurations.
    """
    table = db.table("configurations")
    return table.all()

@router.delete("/{name}")
async def delete_configuration(
    name: str,
    db: TinyDB = Depends(get_client)
):
    """
    Delete a configuration by its name.
    """
    config_model = Configuration(db)
    if config_model.get(name) is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    config_model.delete(name)
    return {"message": f"Configuration '{name}' deleted successfully!"}