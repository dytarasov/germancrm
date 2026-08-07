from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from crm.presentation.schemas.orders import OrderListItemOut


class ClientCreate(BaseModel):
    name: str = Field(min_length=1)
    contacts: str | None = None
    telegram_url: str | None = None
    note: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    contacts: str | None = None
    telegram_url: str | None = None
    note: str | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    contacts: str | None
    telegram_url: str | None
    note: str | None
    created_at: datetime


class ClientListItemOut(BaseModel):
    id: int
    name: str
    contacts: str | None
    telegram_url: str | None
    active_orders: int
    debt_usd: Decimal


class ClientDetailOut(BaseModel):
    client: ClientOut
    orders: list[OrderListItemOut]
    debt_usd: Decimal
    earned_usd: Decimal
