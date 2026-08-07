from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from crm.presentation.schemas.tracks import TrackOut


class EmailRowOut(BaseModel):
    id: int
    from_addr: str
    subject: str | None
    sent_at: datetime | None
    processing_status: str
    error: str | None
    snippet: str | None
    event_type: str | None
    confidence: float | None


class EmailDetailOut(EmailRowOut):
    from_domain: str
    body_text: str | None
    extracted: dict[str, Any] | None


class EmailResolveIn(BaseModel):
    """Ручной разбор письма: заказ обязателен, событие и треки — по желанию."""

    order_id: int
    event_type: Literal["shipped", "arrived_at_warehouse"] | None = None
    tracking_numbers: list[Annotated[str, Field(max_length=64)]] = Field(
        default_factory=list, max_length=20
    )
    carrier: str | None = Field(default=None, max_length=32)


class MailEventOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    event_type: str | None
    summary: str | None
    order_id: int | None
    order_label: str | None
    subject: str | None
    from_addr: str | None


class MailReviewOut(BaseModel):
    emails: list[EmailRowOut]
    filtered: list[EmailRowOut]
    open_tracks: list[TrackOut]


class OAuthUrlOut(BaseModel):
    url: str
