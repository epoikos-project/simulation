import uuid
from typing import Any, Dict, List, Optional, cast
from datetime import datetime, timezone

from loguru import logger
from pydantic import BaseModel, Field

class ConfigurationData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    agents: List[Dict[str, Any]]
    settings: Dict[str, Any] = {}
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(), nullable=True
    )
    last_used: Optional[str] = Field(default=None, nullable=True)


