import uuid
from typing import Any, Dict, List, Optional, cast
from datetime import datetime, timezone

from loguru import logger
from pydantic import BaseModel, Field
from tinydb import Query, TinyDB


class ConfigurationData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    agents: List[Dict[str, Any]]
    settings: Dict[str, Any] = {}
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(), nullable=True
    )
    last_used: Optional[str] = Field(default=None, nullable=True)


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
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            updated = {
                "id": existing.get("id"),
                "name": config.get("name"),
                "agents": config.get("agents"),
                "settings": config.get("settings"),
                "created_at": existing.get("created_at"),
                "last_used": existing.get("last_used"),
            }
            table.update(updated, doc_ids=[existing.doc_id])
            logger.info(f"Configuration '{name}' updated successfully.")
        else:
            config["created_at"] = now
            config["last_used"] = now
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

    def update_last_used(self, name: str) -> None:
        """
        Update the last_used timestamp for a configuration record by its name (case-insensitive).
        """
        table = self._db.table(self._table_name)
        for document in table.all():
            if document.get("name", "").lower() == name.lower():
                now = datetime.now(timezone.utc).isoformat()
                table.update({"last_used": now}, doc_ids=[document.doc_id])
                logger.info(f"Configuration '{name}' last_used updated to {now}.")
                break
