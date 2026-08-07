from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from crm.presentation.schemas.orders import OrderListItemOut
from crm.presentation.schemas.tracks import TrackOut


class MailHealthOut(BaseModel):
    configured: bool
    gmail_connected: bool
    gmail_email: str | None
    needs_reauth: bool
    last_success_at: datetime | None
    llm_degraded: bool
    pending_llm: int
    manual_review: int
    poison: int
    open_tracks: int
    worker_ok: bool


class AttentionOut(BaseModel):
    no_commission: list[OrderListItemOut]
    overdue: list[OrderListItemOut]
    unmatched_tracks: list[TrackOut]


class DashboardOut(BaseModel):
    orders_in_progress: int
    clients_debt_usd: Decimal
    month_profit_usd: Decimal
    month_commissions_usd: Decimal
    month_flights_cost_usd: Decimal
    attention: AttentionOut
    mail: MailHealthOut
