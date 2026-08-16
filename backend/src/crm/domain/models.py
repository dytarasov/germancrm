"""Доменные модели: чистые dataclasses, без pydantic и без знания о БД."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from crm.domain.enums import (
    EmailAction,
    EmailEventType,
    EmailProcessingStatus,
    OrderStatus,
    StatusSource,
    TrackMatchStatus,
    TrackSource,
)


@dataclass(frozen=True, slots=True)
class Client:
    id: int
    name: str
    contacts: str | None
    telegram_url: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ClientListItem:
    client: Client
    active_orders: int
    debt_usd: Decimal


@dataclass(frozen=True, slots=True)
class ClientStats:
    debt_usd: Decimal
    earned_usd: Decimal
    active_orders: int


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    client_id: int
    store: str
    items: str
    purchase_price_usd: Decimal
    commission_usd: Decimal | None  # None = «ещё не знаю», 0 = «без наценки»
    weight_kg: Decimal | None  # фактический, после взвешивания
    est_weight_kg: Decimal | None  # прогноз при создании; комиссия от него — лишь ориентир
    promised_date: date | None
    comment: str | None
    status: OrderStatus
    refunded_amount_usd: Decimal | None
    refunded_at: datetime | None
    flight_id: int | None
    copied_from: int | None
    purchased_on: date
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Suborder:
    """Подзаказ: заказ магазина внутри корзины — номер, справочная сумма и
    собственный статус физического пути. Деньги живут на заказе-корзине."""

    id: int
    order_id: int
    store_order_number: str | None
    amount_usd: Decimal | None
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    eta_on: date | None = None  # ожидаемое прибытие посылки (из писем магазина)


@dataclass(frozen=True, slots=True)
class OrderItem:
    """Позиция составного заказа: название и/или ссылка на товар."""

    id: int
    order_id: int
    title: str | None
    url: str | None
    quantity: int
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OrderListRow:
    """Заказ + агрегаты для списков (одним SQL-запросом)."""

    order: Order
    client_name: str
    paid_usd: Decimal
    tracks_count: int
    suborders_count: int = 1
    # номера заказов магазина по всем подзаказам (без NULL), в порядке создания
    order_numbers: list[str] = field(default_factory=list)
    # ближайший «горизонт» прибытия: MAX(eta_on) по посылкам, что ещё едут к складу
    eta_on: date | None = None


@dataclass(frozen=True, slots=True)
class OrderFinance:
    revenue_usd: Decimal | None  # None, пока комиссия не задана
    paid_usd: Decimal
    due_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class TrackCandidate:
    order_id: int
    score: int
    reasons: list[str]
    order_label: str


@dataclass(frozen=True, slots=True)
class Track:
    id: int
    tracking_number: str
    carrier: str | None
    order_id: int | None
    suborder_id: int | None
    source: TrackSource
    email_log_id: int | None
    match_status: TrackMatchStatus
    candidates: list[TrackCandidate] | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class Payment:
    id: int
    order_id: int
    paid_on: date
    amount_usd: Decimal
    comment: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Flight:
    id: int
    departed_on: date
    cost_usd: Decimal
    description: str | None
    created_at: datetime
    updated_at: datetime
    orders_count: int = 0


@dataclass(frozen=True, slots=True)
class StatusChange:
    id: int
    order_id: int
    old_status: OrderStatus | None
    new_status: OrderStatus
    source: StatusSource
    email_log_id: int | None
    comment: str | None
    changed_at: datetime
    suborder_id: int | None = None  # смена уровня подзаказа


# ---------- Почтовая подсистема ----------


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """Письмо, полученное из Gmail (до записи в лог)."""

    gmail_message_id: str
    gmail_thread_id: str | None
    message_id_hdr: str | None
    from_addr: str
    from_domain: str
    subject: str | None
    sent_at: datetime | None
    snippet: str | None
    body_text: str | None


@dataclass(frozen=True, slots=True)
class EmailLogEntry:
    id: int
    gmail_message_id: str
    from_addr: str
    from_domain: str
    subject: str | None
    sent_at: datetime | None
    snippet: str | None
    body_text: str | None
    processing_status: EmailProcessingStatus
    attempts: int
    next_attempt_at: datetime | None
    error: str | None
    event_type: str | None
    confidence: Decimal | None
    extracted: dict[str, Any] | None
    processed_at: datetime | None
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class EmailEventRow:
    id: int
    email_id: int
    event_type: str | None
    order_id: int | None
    action: EmailAction
    details: dict[str, Any] | None
    created_at: datetime
    subject: str | None = None
    from_addr: str | None = None
    order_label: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedTrack:
    number: str
    carrier: str | None


@dataclass(frozen=True, slots=True)
class EmailExtraction:
    """Валидированный результат LLM-разбора письма."""

    event_type: EmailEventType
    confidence: float
    store_domain: str | None
    order_number: str | None
    tracking_numbers: list[ExtractedTrack]
    carrier: str | None
    summary: str
    reasoning: str | None = None  # объяснение модели — для UI и отладки точности
    eta: str | None = None  # ожидаемая дата доставки (YYYY-MM-DD), если письмо назвало


@dataclass(frozen=True, slots=True)
class LLMUsage:
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: Decimal | None
    attempts: int


@dataclass(frozen=True, slots=True)
class GmailCredentials:
    email_address: str | None
    refresh_token: str
    access_token: str | None
    access_token_expires_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class GmailSyncState:
    history_id: int | None
    last_poll_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    llm_degraded: bool


@dataclass(frozen=True, slots=True)
class MailHealth:
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


@dataclass(frozen=True, slots=True)
class DashboardNumbers:
    orders_in_progress: int
    clients_debt_usd: Decimal
    month_commissions_usd: Decimal
    month_flights_cost_usd: Decimal

    @property
    def month_profit_usd(self) -> Decimal:
        return self.month_commissions_usd - self.month_flights_cost_usd


@dataclass(frozen=True, slots=True)
class MonthMoneyRow:
    month: str  # "2026-08"
    commissions_usd: Decimal
    flights_cost_usd: Decimal

    @property
    def profit_usd(self) -> Decimal:
        return self.commissions_usd - self.flights_cost_usd


@dataclass(frozen=True, slots=True)
class MoneyReportOrderRow:
    id: int
    client_name: str
    store: str
    items: str
    commission_usd: Decimal
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class LoginBan:
    ip: str
    fails: int
    last_fail_at: datetime
    banned_until: datetime | None
