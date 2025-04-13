from tinydb import TinyDB, Query
from loguru import logger
from typing import Optional, Dict

from pydantic import BaseModel
from typing import List, Dict, Any

class ConfigurationData(BaseModel):
    agents: List[Dict[str, Any]]
    settings: Dict[str, Any]
    # Add additional fields as needed.

class Configuration:
    def __init__(self, db: TinyDB) -> None:
        """
        Initialize with a TinyDB instance.
        
        Args:
            db (TinyDB): The TinyDB instance.
        """
        self._db = db
        # You can retrieve the configuration table name from settings, e.g.:
        # self._table_name = settings.tinydb.tables.configuration_table
        # For simplicity, we'll use a hardcoded table name:
        self._table_name = "configurations"

    def save(self, config: Dict) -> None:
        """
        Save or update the configuration JSON.
        
        This method removes any existing configuration before inserting
        the new one, assuming you have a single configuration record.
        
        Args:
            config (dict): The configuration data to save.
        """
        table = self._db.table(self._table_name)
        # If only one configuration should exist, clear any old records
        table.truncate()
        table.insert(config)
        logger.info("Configuration saved successfully.")

    def get(self) -> Optional[Dict]:
        """
        Retrieve the configuration JSON from the database.
        
        Returns:
            dict or None: The configuration if found; otherwise, None.
        """
        table = self._db.table(self._table_name)
        results = table.all()
        if results:
            # Assume only one configuration exists.
            return results[0]
        return None

    def delete(self) -> None:
        """
        Delete the configuration from the database.
        """
        table = self._db.table(self._table_name)
        table.truncate()
        logger.info("Configuration deleted successfully.")