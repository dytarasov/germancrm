from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from crm.domain.enums import OrderStatus
from crm.presentation.schemas.payments import PaymentOut
from crm.presentation.schemas.tracks import TrackOut


class OrderCreate(BaseModel):
    client_id: int
    store: str = Field(min_length=1)
    items: str = Field(min_length=1)
    purchase_price_usd: Decimal = Field(ge=0)
    commission_usd: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    weight_is_final: bool = False
    promised_date: date | None = None
    comment: str | None = None
    store_order_number: str | None = None
    flight_id: int | None = None
    purchased_on: date | None = None
    # ссылки на товары: каждая станет позицией заказа
    links: list[str] = Field(default_factory=list)


class OrderItemCreate(BaseModel):
    title: str | None = None
    url: str | None = None
    quantity: int = Field(default=1, ge=1, le=999)
    note: str | None = None


class OrderItemUpdate(BaseModel):
    title: str | None = None
    url: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=999)
    note: str | None = None


class OrderItemOut(BaseModel):
    id: int
    order_id: int
    title: str | None
    url: str | None
    quantity: int
    note: str | None


class OrderUpdate(BaseModel):
    """PATCH: непереданное поле не трогаем, переданный null — записываем NULL."""

    client_id: int | None = None
    store: str | None = Field(default=None, min_length=1)
    items: str | None = Field(default=None, min_length=1)
    purchase_price_usd: Decimal | None = Field(default=None, ge=0)
    commission_usd: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    weight_is_final: bool | None = None
    promised_date: date | None = None
    comment: str | None = None
    store_order_number: str | None = None
    flight_id: int | None = None
    purchased_on: date | None = None


class StatusChangeIn(BaseModel):
    status: OrderStatus
    comment: str | None = None


class RefundIn(BaseModel):
    refunded_amount_usd: Decimal = Field(ge=0)
    commission_usd: Decimal | None = Field(default=None, ge=0)


class FinanceOut(BaseModel):
    revenue_usd: Decimal | None
    paid_usd: Decimal
    due_usd: Decimal | None


class StatusChangeOut(BaseModel):
    id: int
    old_status: str | None
    new_status: str
    source: str
    comment: str | None
    changed_at: datetime


class OrderListItemOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    store: str
    store_order_number: str | None
    items: str
    status: str
    purchase_price_usd: Decimal
    commission_usd: Decimal | None
    weight_kg: Decimal | None
    promised_date: date | None
    purchased_on: date
    is_overdue: bool
    paid_usd: Decimal
    due_usd: Decimal | None
    tracks_count: int


class OrderDetailOut(OrderListItemOut):
    weight_is_final: bool
    comment: str | None
    refunded_amount_usd: Decimal | None
    refunded_at: datetime | None
    flight_id: int | None
    copied_from: int | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tracks: list[TrackOut]
    payments: list[PaymentOut]
    history: list[StatusChangeOut]
    order_items: list[OrderItemOut]
    finance: FinanceOut
