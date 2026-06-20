"""Customer response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class CustomerOut(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    wa_phone: str
    name: str | None
    default_address: str | None
    order_count: int
    last_order_at: datetime | None
    marketing_opt_in: bool
    created_at: datetime
