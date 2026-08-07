from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    amount_usd: Decimal = Field(gt=0)
    paid_on: date | None = None
    comment: str | None = None


class PaymentUpdate(BaseModel):
    amount_usd: Decimal | None = Field(default=None, gt=0)
    paid_on: date | None = None
    comment: str | None = None


class PaymentOut(BaseModel):
    id: int
    order_id: int
    paid_on: date
    amount_usd: Decimal
    comment: str | None
