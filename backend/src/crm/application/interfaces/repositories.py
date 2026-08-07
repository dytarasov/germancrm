"""Порты репозиториев (Protocol). Реализации — в infrastructure/repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from crm.domain.enums import EmailProcessingStatus, OrderStatus
from crm.domain.models import (
    Client,
    ClientListItem,
    ClientStats,
    DashboardNumbers,
    EmailEventRow,
    EmailLogEntry,
    EmailMessage,
    Flight,
    GmailCredentials,
    GmailSyncState,
    MoneyReportOrderRow,
    MonthMoneyRow,
    Order,
    OrderItem,
    OrderListRow,
    Payment,
    StatusChange,
    Track,
)


@dataclass(slots=True)
class OrderFilters:
    status: OrderStatus | None = None
    client_id: int | None = None
    active: bool | None = None
    overdue: bool = False
    no_commission: bool = False
    search: str | None = None
    flight_id: int | None = None


class ClientRepository(Protocol):
    async def add(
        self, *, name: str, contacts: str | None, telegram_url: str | None, note: str | None
    ) -> Client: ...

    async def get(self, client_id: int) -> Client | None: ...

    async def list(self, search: str | None = None) -> list[ClientListItem]: ...

    async def update(self, client_id: int, fields: dict[str, Any]) -> Client | None: ...

    async def delete(self, client_id: int) -> None: ...

    async def stats(self, client_id: int) -> ClientStats: ...


class OrderRepository(Protocol):
    async def add(self, fields: dict[str, Any]) -> Order: ...

    async def get(self, order_id: int, *, for_update: bool = False) -> Order | None: ...

    async def get_row(self, order_id: int) -> OrderListRow | None: ...

    async def list(self, filters: OrderFilters) -> list[OrderListRow]: ...

    async def update_fields(self, order_id: int, fields: dict[str, Any]) -> None: ...

    async def delete(self, order_id: int) -> None: ...

    async def candidates_for_matching(
        self, *, statuses: list[OrderStatus], max_age_days: int
    ) -> list[OrderListRow]: ...


class OrderItemRepository(Protocol):
    async def add(
        self,
        *,
        order_id: int,
        title: str | None,
        url: str | None,
        quantity: int = 1,
        note: str | None = None,
    ) -> OrderItem: ...

    async def get(self, item_id: int) -> OrderItem | None: ...

    async def list_for_order(self, order_id: int) -> list[OrderItem]: ...

    async def update(self, item_id: int, fields: dict[str, Any]) -> OrderItem | None: ...

    async def delete(self, item_id: int) -> None: ...


class TrackRepository(Protocol):
    async def add(
        self,
        *,
        tracking_number: str,
        carrier: str | None,
        order_id: int | None,
        source: str,
        email_log_id: int | None,
        match_status: str,
        candidates: list[dict[str, Any]] | None,
        note: str | None,
    ) -> Track: ...

    async def get(self, track_id: int) -> Track | None: ...

    async def get_by_number(self, tracking_number: str) -> Track | None: ...

    async def list(
        self, *, unmatched: bool | None = None, search: str | None = None
    ) -> list[Track]: ...

    async def list_for_order(self, order_id: int) -> list[Track]: ...

    async def update(self, track_id: int, fields: dict[str, Any]) -> Track | None: ...

    async def delete(self, track_id: int) -> None: ...

    async def open_tracks(self) -> list[Track]: ...


class PaymentRepository(Protocol):
    async def add(
        self, *, order_id: int, paid_on: date, amount_usd: Decimal, comment: str | None
    ) -> Payment: ...

    async def get(self, payment_id: int) -> Payment | None: ...

    async def list_for_order(self, order_id: int) -> list[Payment]: ...

    async def list(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        client_id: int | None = None,
    ) -> list[Payment]: ...

    async def update(self, payment_id: int, fields: dict[str, Any]) -> Payment | None: ...

    async def delete(self, payment_id: int) -> None: ...

    async def sum_for_order(self, order_id: int) -> Decimal: ...


class FlightRepository(Protocol):
    async def add(
        self, *, departed_on: date, cost_usd: Decimal, description: str | None
    ) -> Flight: ...

    async def get(self, flight_id: int) -> Flight | None: ...

    async def list(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[Flight]: ...

    async def update(self, flight_id: int, fields: dict[str, Any]) -> Flight | None: ...

    async def delete(self, flight_id: int) -> None: ...


class StatusHistoryRepository(Protocol):
    async def add(
        self,
        *,
        order_id: int,
        old_status: OrderStatus | None,
        new_status: OrderStatus,
        source: str,
        email_log_id: int | None = None,
        comment: str | None = None,
    ) -> StatusChange: ...

    async def list_for_order(self, order_id: int) -> list[StatusChange]: ...


class DashboardRepository(Protocol):
    async def numbers(self, *, month_start: date, month_end_excl: date) -> DashboardNumbers: ...


class ReportRepository(Protocol):
    async def totals(self, date_from: date, date_to: date) -> tuple[Decimal, Decimal]:
        """(комиссии закрытых/refunded за период, стоимость рейсов за период)."""
        ...

    async def money_orders(self, date_from: date, date_to: date) -> list[MoneyReportOrderRow]: ...

    async def months(self, date_from: date, date_to: date) -> list[MonthMoneyRow]: ...


class SettingsRepository(Protocol):
    async def all(self) -> dict[str, Any]: ...

    async def get(self, key: str) -> Any | None: ...

    async def set_many(self, values: dict[str, Any]) -> None: ...


class GmailStateRepository(Protocol):
    async def get_credentials(self) -> GmailCredentials | None: ...

    async def save_credentials(
        self,
        *,
        email_address: str | None,
        refresh_token: str,
        access_token: str | None,
        expires_at: datetime | None,
    ) -> None: ...

    async def update_access_token(self, access_token: str, expires_at: datetime) -> None: ...

    async def mark_revoked(self) -> None: ...

    async def get_sync_state(self) -> GmailSyncState: ...

    async def update_sync_state(self, fields: dict[str, Any]) -> None: ...


class EmailRepository(Protocol):
    async def insert_ingested(
        self, msg: EmailMessage, status: EmailProcessingStatus
    ) -> int | None:
        """None, если письмо уже есть (дедуп)."""
        ...

    async def get(self, email_id: int) -> EmailLogEntry | None: ...

    async def fetch_queue(self, *, now: datetime, limit: int) -> list[EmailLogEntry]: ...

    async def update(self, email_id: int, fields: dict[str, Any]) -> None: ...

    async def add_event(
        self,
        *,
        email_id: int,
        event_type: str | None,
        order_id: int | None,
        action: str,
        details: dict[str, Any] | None,
    ) -> None: ...

    async def list_events(self, limit: int) -> list[EmailEventRow]: ...

    async def list_by_status(
        self, statuses: list[EmailProcessingStatus], limit: int
    ) -> list[EmailLogEntry]: ...

    async def list_all(
        self,
        *,
        status: EmailProcessingStatus | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[EmailLogEntry]: ...

    async def events_for_email(self, email_id: int) -> list[EmailEventRow]: ...

    async def status_counts(self) -> dict[str, int]: ...

    async def requeue_filtered_domain(self, domain: str) -> int: ...
