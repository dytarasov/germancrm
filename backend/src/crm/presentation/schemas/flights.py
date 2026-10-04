from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from crm.presentation.schemas.orders import OrderListItemOut


class FlightCreate(BaseModel):
    departed_on: date
    cost_usd: Decimal = Field(ge=0)
    description: str | None = None


class FlightUpdate(BaseModel):
    departed_on: date | None = None
    cost_usd: Decimal | None = Field(default=None, ge=0)
    description: str | None = None


class FlightAssign(BaseModel):
    add: list[int] = Field(default_factory=list, max_length=500)
    remove: list[int] = Field(default_factory=list, max_length=500)


class FlightOut(BaseModel):
    id: int
    departed_on: date
    cost_usd: Decimal
    description: str | None
    orders_count: int


class FlightDetailOut(FlightOut):
    orders: list[OrderListItemOut]
