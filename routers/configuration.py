import asyncio
from fastapi import APIRouter, HTTPException
from loguru import logger
from clients import DB  # This is your dependency providing a TinyDB instance
from models.configuration import Configuration, ConfigurationData
router = APIRouter(prefix="/configuration", tags=["Configuration"])

@router.post("")
async def save_configuration(config: ConfigurationData, db: DB):
    """
    Saves the configuration JSON data to the configurations table.
    """
    try:
        config_model = Configuration(db)
        # Save the configuration (this internally truncates the table before inserting)
        config_model.save(config.dict())
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return {"message": "Error saving configuration"}
    return {"message": "Configuration saved successfully!"}


@router.get("")
async def get_configuration(db: DB):
    """
    Retrieves the configuration JSON from the database.
    """
    try:
        config_model = Configuration(db)
        config_data = config_model.get()
        if config_data is None:
            raise HTTPException(status_code=404, detail="Configuration not found")
    except Exception as e:
        logger.error(f"Error getting configuration: {e}")
        return {"message": "Error getting configuration"}
    return config_data


@router.delete("")
async def delete_configuration(db: DB):
    """
    Deletes the configuration JSON from the configurations table.
    """
    try:
        config_model = Configuration(db)
        config_model.delete()
    except Exception as e:
        logger.error(f"Error deleting configuration: {e}")
        return {"message": "Error deleting configuration"}
    return {"message": "Configuration deleted successfully!"}
