import uuid
from typing import Any, Dict, List, Optional, cast

from loguru import logger
from pydantic import BaseModel, Field
from tinydb import Query, TinyDB


class ConfigurationData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    agents: List[Dict[str, Any]]
    settings: Dict[str, Any] = {}


class Configuration:
    def __init__(self, db: TinyDB) -> None:
        """Initialize with a TinyDB instance."""
        self._db = db
        self._table_name = "configurations"

    def save(self, config: Dict[str, Any]) -> None:
        """
        Save or update the configuration record.
        If a configuration with the given name (case-insensitive) exists, update it;
        otherwise, insert a new configuration.
        """
        name = config.get("name")
        if not name:
            raise ValueError("Configuration must have a name")
        table = self._db.table(self._table_name)
        q = Query()
        existing = None
        for document in table.all():
            if document.get("name", "").lower() == name.lower():
                existing = document
                break
        if existing:
            table.update(config, doc_ids=[existing.doc_id])
            logger.info(f"Configuration '{name}' updated successfully.")
        else:
            table.insert(config)
            logger.info(f"Configuration '{name}' saved successfully.")

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a configuration record by its name (case-insensitive).
        """
        table = self._db.table(self._table_name)
        for document in table.all():
            if document.get("name", "").lower() == name.lower():
                return document
        return None

    def delete(self, name: str) -> None:
        """
        Delete a configuration record by its name (case-insensitive).
        """
        table = self._db.table(self._table_name)
        to_remove = [
            document.doc_id
            for document in table.all()
            if document.get("name", "").lower() == name.lower()
        ]
        if to_remove:
            table.remove(doc_ids=to_remove)
            logger.info(f"Configuration '{name}' deleted successfully.")
