"""Shared Pydantic base classes."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Response model base that reads from SQLAlchemy ORM objects."""

    model_config = ConfigDict(from_attributes=True)
