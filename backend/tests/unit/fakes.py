"""In-memory фейки портов для unit-тестов сервисов."""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from crm.application.interfaces.repositories import OrderFilters
from crm.application.services.matching import normalize_number
from crm.domain.enums import (
    EmailProcessingStatus,
    OrderStatus,
    StatusSource,
    TrackMatchStatus,
    TrackSource,
)
from crm.domain.models import (
    EmailLogEntry,
    EmailMessage,
    GmailCredentials,
    GmailSyncState,
    Order,
    OrderItem,
    OrderListRow,
    Payment,
    StatusChange,
    Suborder,
    Track,
    TrackCandidate,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
TODAY = date(2026, 8, 6)


def make_order(**overrides: Any) -> Order:
    defaults: dict[str, Any] = {
        "id": 1,
        "client_id": 1,
        "store": "Amazon",
        "items": "iPhone 17 Pro",
        "purchase_price_usd": Decimal("1000.00"),
        "commission_usd": None,
        "weight_kg": None,
        "est_weight_kg": None,
        "promised_date": None,
        "comment": None,
        "status": OrderStatus.PURCHASED,
        "refunded_amount_usd": None,
        "refunded_at": None,
        "flight_id": None,
        "copied_from": None,
        "purchased_on": TODAY,
        "closed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(overrides)
    return Order(**defaults)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        self.entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.exited += 1


class FakeSuborderRepository:
    def __init__(self) -> None:
        self.storage: dict[int, Suborder] = {}
        self._ids = itertools.count(1)

    def seed(
        self,
        *,
        order_id: int,
        store_order_number: str | None = None,
        amount_usd: Decimal | None = None,
        status: OrderStatus = OrderStatus.PURCHASED,
    ) -> Suborder:
        sub = Suborder(
            id=next(self._ids),
            order_id=order_id,
            store_order_number=store_order_number,
            amount_usd=amount_usd,
            status=status,
            created_at=NOW,
            updated_at=NOW,
        )
        self.storage[sub.id] = sub
        return sub

    async def add(
        self,
        *,
        order_id: int,
        store_order_number: str | None,
        amount_usd: Decimal | None,
        status: OrderStatus = OrderStatus.PURCHASED,
    ) -> Suborder:
        return self.seed(
            order_id=order_id,
            store_order_number=store_order_number,
            amount_usd=amount_usd,
            status=status,
        )

    async def get(self, suborder_id: int, *, for_update: bool = False) -> Suborder | None:
        return self.storage.get(suborder_id)

    async def list_for_order(self, order_id: int) -> list[Suborder]:
        return sorted(
            (s for s in self.storage.values() if s.order_id == order_id),
            key=lambda s: s.id,
        )

    async def update(self, suborder_id: int, fields: dict[str, Any]) -> Suborder | None:
        sub = self.storage.get(suborder_id)
        if sub is None:
            return None
        fields = dict(fields)
        if "status" in fields:
            fields["status"] = OrderStatus(str(fields["status"]))
        self.storage[suborder_id] = replace(sub, **fields)
        return self.storage[suborder_id]

    async def delete(self, suborder_id: int) -> None:
        self.storage.pop(suborder_id, None)

    async def find_by_number(self, normalized_number: str) -> list[Suborder]:
        if not normalized_number:
            return []
        return sorted(
            (
                s
                for s in self.storage.values()
                if s.store_order_number
                and normalize_number(s.store_order_number) == normalized_number
            ),
            key=lambda s: s.id,
        )


class FakeOrderRepository:
    def __init__(self, suborders: FakeSuborderRepository | None = None) -> None:
        self.storage: dict[int, Order] = {}
        self.client_names: dict[int, str] = {1: "Иванов"}
        self.suborders = suborders
        self._ids = itertools.count(1)

    def seed(self, order: Order, *, order_number: str | None = None) -> Order:
        self.storage[order.id] = order
        # как миграция 0006: у каждого заказа есть хотя бы один подзаказ
        if self.suborders is not None and not any(
            s.order_id == order.id for s in self.suborders.storage.values()
        ):
            sub_status = {
                OrderStatus.CLOSED: OrderStatus.DELIVERED,
                OrderStatus.REFUNDED: OrderStatus.CANCELLED,
            }.get(order.status, order.status)
            self.suborders.seed(
                order_id=order.id, store_order_number=order_number, status=sub_status
            )
        return order

    async def add(self, fields: dict[str, Any]) -> Order:
        new_id = max(self.storage.keys(), default=0) + 1
        order = make_order(id=new_id, **fields)
        self.storage[order.id] = order
        return order

    async def get(self, order_id: int, *, for_update: bool = False) -> Order | None:
        return self.storage.get(order_id)

    async def get_row(self, order_id: int) -> OrderListRow | None:
        order = self.storage.get(order_id)
        if order is None:
            return None
        return self._row(order)

    async def list(self, filters: OrderFilters) -> list[OrderListRow]:
        rows = [self._row(o) for o in self.storage.values()]
        if filters.client_id is not None:
            rows = [r for r in rows if r.order.client_id == filters.client_id]
        if filters.status is not None:
            rows = [r for r in rows if r.order.status == filters.status]
        return rows

    async def update_fields(self, order_id: int, fields: dict[str, Any]) -> None:
        order = self.storage[order_id]
        self.storage[order_id] = replace(order, **fields)

    async def delete(self, order_id: int) -> None:
        self.storage.pop(order_id, None)

    async def candidates_for_matching(
        self, *, statuses: list[OrderStatus], max_age_days: int
    ) -> list[OrderListRow]:
        return [self._row(o) for o in self.storage.values() if o.status in statuses]

    def _row(self, order: Order) -> OrderListRow:
        subs: list[Suborder] = []
        if self.suborders is not None:
            subs = sorted(
                (s for s in self.suborders.storage.values() if s.order_id == order.id),
                key=lambda s: s.id,
            )
        return OrderListRow(
            order=order,
            client_name=self.client_names.get(order.client_id, "Клиент"),
            paid_usd=Decimal("0"),
            tracks_count=0,
            suborders_count=len(subs) if subs else 1,
            order_numbers=[s.store_order_number for s in subs if s.store_order_number],
        )


class FakeOrderItemRepository:
    def __init__(self) -> None:
        self.storage: dict[int, OrderItem] = {}
        self._ids = itertools.count(1)

    async def add(
        self,
        *,
        order_id: int,
        title: str | None,
        url: str | None,
        quantity: int = 1,
        note: str | None = None,
    ) -> OrderItem:
        item = OrderItem(
            id=next(self._ids),
            order_id=order_id,
            title=title,
            url=url,
            quantity=quantity,
            note=note,
            created_at=NOW,
        )
        self.storage[item.id] = item
        return item

    async def get(self, item_id: int) -> OrderItem | None:
        return self.storage.get(item_id)

    async def list_for_order(self, order_id: int) -> list[OrderItem]:
        return [i for i in self.storage.values() if i.order_id == order_id]

    async def update(self, item_id: int, fields: dict[str, Any]) -> OrderItem | None:
        item = self.storage.get(item_id)
        if item is None:
            return None
        self.storage[item_id] = replace(item, **fields)
        return self.storage[item_id]

    async def delete(self, item_id: int) -> None:
        self.storage.pop(item_id, None)


class FakeTrackRepository:
    def __init__(self) -> None:
        self.storage: dict[int, Track] = {}
        self._ids = itertools.count(1)

    async def add(self, **kwargs: Any) -> Track:
        candidates_raw = kwargs.get("candidates")
        track = Track(
            id=next(self._ids),
            tracking_number=kwargs["tracking_number"],
            carrier=kwargs.get("carrier"),
            order_id=kwargs.get("order_id"),
            suborder_id=kwargs.get("suborder_id"),
            source=TrackSource(str(kwargs.get("source", "manual"))),
            email_log_id=kwargs.get("email_log_id"),
            match_status=TrackMatchStatus(str(kwargs.get("match_status", "linked"))),
            candidates=(
                [TrackCandidate(**c) for c in candidates_raw] if candidates_raw else None
            ),
            note=kwargs.get("note"),
            created_at=NOW,
            updated_at=NOW,
            resolved_at=None,
        )
        self.storage[track.id] = track
        return track

    async def get(self, track_id: int) -> Track | None:
        return self.storage.get(track_id)

    async def get_by_number(self, tracking_number: str) -> Track | None:
        for t in self.storage.values():
            if t.tracking_number == tracking_number:
                return t
        return None

    async def list(self, *, unmatched: bool | None = None, search: str | None = None) -> list[Track]:
        tracks = list(self.storage.values())
        if unmatched:
            tracks = [t for t in tracks if t.match_status == TrackMatchStatus.OPEN]
        return tracks

    async def list_for_order(self, order_id: int) -> list[Track]:
        return [t for t in self.storage.values() if t.order_id == order_id]

    async def update(self, track_id: int, fields: dict[str, Any]) -> Track | None:
        track = self.storage.get(track_id)
        if track is None:
            return None
        fields = dict(fields)
        if "match_status" in fields:
            fields["match_status"] = TrackMatchStatus(str(fields["match_status"]))
        if "candidates" in fields and fields["candidates"]:
            fields["candidates"] = [TrackCandidate(**c) for c in fields["candidates"]]
        self.storage[track_id] = replace(track, **fields)
        return self.storage[track_id]

    async def delete(self, track_id: int) -> None:
        self.storage.pop(track_id, None)

    async def open_tracks(self) -> list[Track]:
        return [t for t in self.storage.values() if t.match_status == TrackMatchStatus.OPEN]


class FakePaymentRepository:
    def __init__(self) -> None:
        self.storage: dict[int, Payment] = {}
        self._ids = itertools.count(1)

    async def add(self, *, order_id, paid_on, amount_usd, comment) -> Payment:
        p = Payment(
            id=next(self._ids),
            order_id=order_id,
            paid_on=paid_on,
            amount_usd=amount_usd,
            comment=comment,
            created_at=NOW,
        )
        self.storage[p.id] = p
        return p

    async def get(self, payment_id: int) -> Payment | None:
        return self.storage.get(payment_id)

    async def list_for_order(self, order_id: int) -> list[Payment]:
        return [p for p in self.storage.values() if p.order_id == order_id]

    async def list(self, **kwargs) -> list[Payment]:
        return list(self.storage.values())

    async def update(self, payment_id: int, fields: dict[str, Any]) -> Payment | None:
        p = self.storage.get(payment_id)
        if p is None:
            return None
        self.storage[payment_id] = replace(p, **fields)
        return self.storage[payment_id]

    async def delete(self, payment_id: int) -> None:
        self.storage.pop(payment_id, None)

    async def sum_for_order(self, order_id: int) -> Decimal:
        return sum(
            (p.amount_usd for p in self.storage.values() if p.order_id == order_id),
            Decimal("0"),
        )


class FakeStatusHistoryRepository:
    def __init__(self) -> None:
        self.entries: list[StatusChange] = []
        self._ids = itertools.count(1)

    async def add(
        self,
        *,
        order_id,
        old_status,
        new_status,
        source,
        email_log_id=None,
        comment=None,
        suborder_id=None,
    ) -> StatusChange:
        change = StatusChange(
            id=next(self._ids),
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            source=StatusSource(str(source)),
            email_log_id=email_log_id,
            comment=comment,
            changed_at=NOW,
            suborder_id=suborder_id,
        )
        self.entries.append(change)
        return change

    async def list_for_order(self, order_id: int) -> list[StatusChange]:
        return [e for e in self.entries if e.order_id == order_id]


class FakeSettingsRepository:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values: dict[str, Any] = values or {}

    async def all(self) -> dict[str, Any]:
        return dict(self.values)

    async def get(self, key: str) -> Any | None:
        return self.values.get(key)

    async def set_many(self, values: dict[str, Any]) -> None:
        self.values.update(values)


class FakeGmailStateRepository:
    def __init__(self) -> None:
        self.credentials: GmailCredentials | None = None
        self.sync_state = GmailSyncState(
            history_id=None,
            last_poll_at=None,
            last_success_at=None,
            last_error=None,
            consecutive_failures=0,
            llm_degraded=False,
        )

    async def get_credentials(self) -> GmailCredentials | None:
        return self.credentials

    async def save_credentials(self, *, email_address, refresh_token, access_token, expires_at):
        self.credentials = GmailCredentials(
            email_address=email_address,
            refresh_token=refresh_token,
            access_token=access_token,
            access_token_expires_at=expires_at,
            revoked_at=None,
        )

    async def update_access_token(self, access_token, expires_at) -> None:
        assert self.credentials is not None
        self.credentials = replace(
            self.credentials,
            access_token=access_token,
            access_token_expires_at=expires_at,
        )

    async def mark_revoked(self) -> None:
        assert self.credentials is not None
        self.credentials = replace(self.credentials, revoked_at=NOW)

    async def get_sync_state(self) -> GmailSyncState:
        return self.sync_state

    async def update_sync_state(self, fields: dict[str, Any]) -> None:
        self.sync_state = replace(self.sync_state, **fields)


class FakeEmailRepository:
    def __init__(self) -> None:
        self.storage: dict[int, EmailLogEntry] = {}
        self.events: list[dict[str, Any]] = []
        self._ids = itertools.count(1)

    def seed_entry(self, **overrides: Any) -> EmailLogEntry:
        entry_id = overrides.pop("id", next(self._ids))
        entry = EmailLogEntry(
            id=entry_id,
            gmail_message_id=overrides.pop("gmail_message_id", f"gm-{entry_id}"),
            from_addr=overrides.pop("from_addr", "ship-confirm@amazon.com"),
            from_domain=overrides.pop("from_domain", "amazon.com"),
            subject=overrides.pop("subject", "Your order has shipped"),
            sent_at=overrides.pop("sent_at", NOW),
            snippet=overrides.pop("snippet", None),
            body_text=overrides.pop("body_text", ""),
            processing_status=overrides.pop("processing_status", EmailProcessingStatus.NEW),
            attempts=overrides.pop("attempts", 0),
            next_attempt_at=overrides.pop("next_attempt_at", None),
            error=overrides.pop("error", None),
            event_type=overrides.pop("event_type", None),
            confidence=overrides.pop("confidence", None),
            extracted=overrides.pop("extracted", None),
            processed_at=overrides.pop("processed_at", None),
            ingested_at=overrides.pop("ingested_at", NOW),
        )
        assert not overrides, f"неизвестные поля: {overrides}"
        self.storage[entry.id] = entry
        return entry

    async def insert_ingested(self, msg: EmailMessage, status) -> int | None:
        for e in self.storage.values():
            if e.gmail_message_id == msg.gmail_message_id:
                return None
        entry = self.seed_entry(
            gmail_message_id=msg.gmail_message_id,
            from_addr=msg.from_addr,
            from_domain=msg.from_domain,
            subject=msg.subject,
            sent_at=msg.sent_at,
            snippet=msg.snippet,
            body_text=msg.body_text,
            processing_status=status,
        )
        return entry.id

    async def get(self, email_id: int, *, for_update: bool = False) -> EmailLogEntry | None:
        return self.storage.get(email_id)

    async def fetch_queue(self, *, now, limit) -> list[EmailLogEntry]:
        return [
            e
            for e in self.storage.values()
            if e.processing_status
            in (EmailProcessingStatus.NEW, EmailProcessingStatus.PENDING_LLM)
            and (e.next_attempt_at is None or e.next_attempt_at <= now)
        ][:limit]

    async def update(self, email_id: int, fields: dict[str, Any]) -> None:
        entry = self.storage[email_id]
        known = {f for f in EmailLogEntry.__dataclass_fields__}
        fields = {k: v for k, v in fields.items() if k in known}
        if "processing_status" in fields:
            fields["processing_status"] = EmailProcessingStatus(
                str(fields["processing_status"])
            )
        if "event_type" in fields and fields["event_type"] is not None:
            fields["event_type"] = str(fields["event_type"])
        self.storage[email_id] = replace(entry, **fields)

    async def add_event(self, **kwargs: Any) -> None:
        self.events.append(kwargs)

    async def list_events(self, limit: int) -> list:
        return []

    async def list_by_status(self, statuses, limit) -> list[EmailLogEntry]:
        return [e for e in self.storage.values() if e.processing_status in statuses]

    async def list_all(self, *, status=None, search=None, limit=100) -> list[EmailLogEntry]:
        entries = list(self.storage.values())
        if status is not None:
            entries = [e for e in entries if e.processing_status == status]
        if search:
            s = search.lower()
            entries = [
                e
                for e in entries
                if s in e.from_addr.lower() or s in (e.subject or "").lower()
            ]
        return entries[:limit]

    async def events_for_email(self, email_id: int) -> list:
        return [e for e in self.events if e.get("email_id") == email_id]

    async def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.storage.values():
            counts[e.processing_status] = counts.get(e.processing_status, 0) + 1
        return counts

    async def requeue_filtered_domain(self, domain: str) -> int:
        return 0
