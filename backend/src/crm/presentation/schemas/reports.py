from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from crm.presentation.schemas.flights import FlightOut


class MoneyOrderRowOut(BaseModel):
    id: int
    client_name: str
    store: str
    items: str
    commission_usd: Decimal
    closed_at: datetime | None


class MonthRowOut(BaseModel):
    month: str
    commissions_usd: Decimal
    flights_cost_usd: Decimal
    profit_usd: Decimal


class MoneyReportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    commissions_usd: Decimal
    flights_cost_usd: Decimal
    profit_usd: Decimal
    orders: list[MoneyOrderRowOut]
    flights: list[FlightOut]
    months: list[MonthRowOut]
