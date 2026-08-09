from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from crm.application.interfaces.repositories import (
    OrderFilters,
    OrderItemRepository,
    OrderRepository,
    PaymentRepository,
    SettingsRepository,
    StatusHistoryRepository,
    TrackRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.domain import rules
from crm.domain.clock import business_today
from crm.domain.enums import OrderStatus, StatusSource, TrackMatchStatus
from crm.domain.exceptions import (
    DomainValidationError,
    InvalidStatusTransitionError,
    NotFoundError,
)
from crm.domain.models import (
    Order,
    OrderFinance,
    OrderItem,
    OrderListRow,
    Payment,
    StatusChange,
    Track,
)

AutoAdvanceOutcome = Literal["advanced", "stale", "terminal", "rejected", "not_found"]


@dataclass(frozen=True, slots=True)
class OrderDetail:
    order: Order
    client_name: str
    paid_usd: Decimal
    tracks_count: int
    tracks: list[Track]
    payments: list[Payment]
    history: list[StatusChange]
    order_items: list[OrderItem]

    @property
    def finance(self) -> OrderFinance:
        o = self.order
        return OrderFinance(
            revenue_usd=rules.revenue_usd(o.purchase_price_usd, o.commission_usd),
            paid_usd=self.paid_usd,
            due_usd=rules.due_usd(o.purchase_price_usd, o.commission_usd, self.paid_usd),
        )


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        items: OrderItemRepository,
        tracks: TrackRepository,
        payments: PaymentRepository,
        history: StatusHistoryRepository,
        app_settings: SettingsRepository,
        uow: UnitOfWork,
    ) -> None:
        self._orders = orders
        self._items = items
        self._tracks = tracks
        self._payments = payments
        self._history = history
        self._app_settings = app_settings
        self._uow = uow

    # ---------- чтение ----------

    async def get_detail(self, order_id: int) -> OrderDetail:
        row = await self._orders.get_row(order_id)
        if row is None:
            raise NotFoundError.entity("Заказ", order_id)
        return OrderDetail(
            order=row.order,
            client_name=row.client_name,
            paid_usd=row.paid_usd,
            tracks_count=row.tracks_count,
            tracks=await self._tracks.list_for_order(order_id),
            payments=await self._payments.list_for_order(order_id),
            history=await self._history.list_for_order(order_id),
            order_items=await self._items.list_for_order(order_id),
        )

    async def list(self, filters: OrderFilters) -> list[OrderListRow]:
        return await self._orders.list(filters)

    # ---------- создание / правка ----------

    async def create(self, fields: dict[str, Any]) -> OrderDetail:
        fields = dict(fields)
        links = [str(u).strip() for u in (fields.pop("links", None) or []) if str(u).strip()]
        fields.setdefault("status", OrderStatus.PURCHASED)
        fields.setdefault("purchased_on", business_today())
        async with self._uow:
            order = await self._orders.add(fields)
            for url in links:
                await self._items.add(order_id=order.id, title=None, url=url)
            await self._history.add(
                order_id=order.id,
                old_status=None,
                new_status=OrderStatus.PURCHASED,
                source=StatusSource.MANUAL,
            )
        return await self.get_detail(order.id)

    async def update(self, order_id: int, fields: dict[str, Any]) -> OrderDetail:
        if not fields:
            return await self.get_detail(order_id)
        async with self._uow:
            order = await self._orders.get(order_id, for_update=True)
            if order is None:
                raise NotFoundError.entity("Заказ", order_id)
            # Комиссию нельзя стереть у закрытого заказа — сломается отчётность.
            if (
                order.status == OrderStatus.CLOSED
                and "commission_usd" in fields
                and fields["commission_usd"] is None
            ):
                raise DomainValidationError(
                    "У закрытого заказа комиссия обязательна: сначала переоткройте заказ"
                )
            # Фактический вес заполняет комиссию по тарифу, но только если её
            # ещё нет и в этом же патче её не задали руками — ручная главнее.
            if (
                fields.get("weight_kg") is not None
                and "commission_usd" not in fields
                and order.commission_usd is None
            ):
                fields["commission_usd"] = rules.suggest_commission(
                    fields["weight_kg"], await self._commission_per_kg()
                )
            await self._orders.update_fields(order_id, fields)
        return await self.get_detail(order_id)

    async def delete(self, order_id: int) -> None:
        async with self._uow:
            if await self._orders.get(order_id, for_update=True) is None:
                raise NotFoundError.entity("Заказ", order_id)
            # треки не удаляем, а возвращаем в очередь непривязанных —
            # иначе они «осиротеют» (linked без заказа) и пропадут из вида;
            # dismissed остаются dismissed: это решение человека
            for track in await self._tracks.list_for_order(order_id):
                if track.match_status == TrackMatchStatus.DISMISSED:
                    await self._tracks.update(track.id, {"order_id": None})
                else:
                    await self._tracks.update(
                        track.id,
                        {
                            "order_id": None,
                            "match_status": TrackMatchStatus.OPEN,
                            "resolved_at": None,
                        },
                    )
            await self._orders.delete(order_id)

    # ---------- статусы (руками) ----------

    async def set_status(
        self, order_id: int, new_status: OrderStatus, *, comment: str | None = None
    ) -> OrderDetail:
        """Ручная смена по линейке (в любую сторону). cancel/refund — отдельными операциями."""
        if new_status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            raise DomainValidationError("Для отмены и возврата используйте отдельные операции")
        async with self._uow:
            order = await self._get_locked(order_id)
            if order.status == new_status:
                pass
            else:
                fields: dict[str, Any] = {"status": new_status}
                if new_status == OrderStatus.CLOSED:
                    rules.ensure_closable(order.commission_usd)
                    fields["closed_at"] = _now()
                if order.status == OrderStatus.CLOSED and new_status != OrderStatus.CLOSED:
                    fields["closed_at"] = None
                if order.status == OrderStatus.REFUNDED:
                    fields["refunded_at"] = None
                await self._orders.update_fields(order_id, fields)
                await self._history.add(
                    order_id=order_id,
                    old_status=order.status,
                    new_status=new_status,
                    source=StatusSource.MANUAL,
                    comment=comment,
                )
        return await self.get_detail(order_id)

    async def close(self, order_id: int) -> OrderDetail:
        return await self.set_status(order_id, OrderStatus.CLOSED)

    async def cancel(self, order_id: int, *, comment: str | None = None) -> OrderDetail:
        async with self._uow:
            order = await self._get_locked(order_id)
            if order.status in (OrderStatus.CLOSED, OrderStatus.REFUNDED):
                raise InvalidStatusTransitionError(
                    "Нельзя отменить закрытый или возвращённый заказ: сначала переоткройте его"
                )
            if order.status != OrderStatus.CANCELLED:
                await self._orders.update_fields(order_id, {"status": OrderStatus.CANCELLED})
                await self._history.add(
                    order_id=order_id,
                    old_status=order.status,
                    new_status=OrderStatus.CANCELLED,
                    source=StatusSource.MANUAL,
                    comment=comment,
                )
        return await self.get_detail(order_id)

    async def refund(
        self,
        order_id: int,
        *,
        refunded_amount_usd: Decimal,
        commission_usd: Decimal | None = None,
        commission_provided: bool = False,
    ) -> OrderDetail:
        if refunded_amount_usd < 0:
            raise DomainValidationError("Сумма возврата не может быть отрицательной")
        async with self._uow:
            order = await self._get_locked(order_id)
            if order.status == OrderStatus.CANCELLED:
                raise InvalidStatusTransitionError("Отменённый заказ нельзя перевести в возврат")
            fields: dict[str, Any] = {"refunded_amount_usd": refunded_amount_usd}
            if commission_provided:
                fields["commission_usd"] = commission_usd
            if order.status != OrderStatus.REFUNDED:
                # refunded_at ставим один раз: повторный refund лишь правит сумму
                # и не перетаскивает комиссию в другой отчётный период.
                fields.update(
                    status=OrderStatus.REFUNDED, refunded_at=_now(), closed_at=None
                )
            await self._orders.update_fields(order_id, fields)
            if order.status != OrderStatus.REFUNDED:
                await self._history.add(
                    order_id=order_id,
                    old_status=order.status,
                    new_status=OrderStatus.REFUNDED,
                    source=StatusSource.MANUAL,
                )
        return await self.get_detail(order_id)

    async def copy(self, order_id: int) -> OrderDetail:
        """Копия для перезаказа после отмены: поля те же, без треков/платежей/номера заказа."""
        async with self._uow:
            src = await self._orders.get(order_id)
            if src is None:
                raise NotFoundError.entity("Заказ", order_id)
            new_order = await self._orders.add(
                {
                    "client_id": src.client_id,
                    "store": src.store,
                    "store_order_number": None,
                    "items": src.items,
                    "purchase_price_usd": src.purchase_price_usd,
                    "commission_usd": src.commission_usd,
                    # факт. вес принадлежит конкретной посылке — в перезаказ идёт только прогноз
                    "weight_kg": None,
                    "est_weight_kg": src.est_weight_kg,
                    "promised_date": src.promised_date,
                    "comment": src.comment,
                    "status": OrderStatus.PURCHASED,
                    "purchased_on": business_today(),
                    "copied_from": src.id,
                }
            )
            # позиции — часть описания покупки, копируем вместе с заказом
            for item in await self._items.list_for_order(src.id):
                await self._items.add(
                    order_id=new_order.id,
                    title=item.title,
                    url=item.url,
                    quantity=item.quantity,
                    note=item.note,
                )
            await self._history.add(
                order_id=new_order.id,
                old_status=None,
                new_status=OrderStatus.PURCHASED,
                source=StatusSource.MANUAL,
            )
        return await self.get_detail(new_order.id)

    # ---------- позиции ----------

    async def add_item(
        self,
        order_id: int,
        *,
        title: str | None = None,
        url: str | None = None,
        quantity: int = 1,
        note: str | None = None,
    ) -> OrderItem:
        title = (title or "").strip() or None
        url = (url or "").strip() or None
        if title is None and url is None:
            raise DomainValidationError("У позиции должно быть название или ссылка")
        async with self._uow:
            if await self._orders.get(order_id) is None:
                raise NotFoundError.entity("Заказ", order_id)
            return await self._items.add(
                order_id=order_id, title=title, url=url, quantity=quantity, note=note
            )

    async def update_item(
        self, order_id: int, item_id: int, fields: dict[str, Any]
    ) -> OrderItem:
        async with self._uow:
            item = await self._get_item(order_id, item_id)
            fields = dict(fields)
            for key in ("title", "url"):
                if key in fields and isinstance(fields[key], str):
                    fields[key] = fields[key].strip() or None
            if (
                fields.get("title", item.title) is None
                and fields.get("url", item.url) is None
            ):
                raise DomainValidationError("У позиции должно быть название или ссылка")
            updated = await self._items.update(item_id, fields)
            assert updated is not None
            return updated

    async def delete_item(self, order_id: int, item_id: int) -> None:
        async with self._uow:
            await self._get_item(order_id, item_id)
            await self._items.delete(item_id)

    async def _get_item(self, order_id: int, item_id: int) -> OrderItem:
        item = await self._items.get(item_id)
        if item is None or item.order_id != order_id:
            raise NotFoundError.entity("Позиция", item_id)
        return item

    # ---------- статусы (автоматика) ----------

    async def advance_status_auto(
        self,
        order_id: int,
        new_status: OrderStatus,
        *,
        email_log_id: int,
        source: StatusSource = StatusSource.AUTO,
    ) -> AutoAdvanceOutcome:
        """Только вперёд, только shipped/at_warehouse, терминальные не трогаем.

        source=MANUAL — когда событие письма применяет человек из очереди разбора:
        правила безопасности те же, но в истории виден настоящий автор решения."""
        async with self._uow:
            order = await self._orders.get(order_id, for_update=True)
            if order is None:
                return "not_found"
            if order.status in rules.TERMINAL_STATUSES:
                return "terminal"
            if new_status not in rules.AUTO_TARGETS:
                return "rejected"
            if rules.flow_index(new_status) <= rules.flow_index(order.status):
                return "stale"
            await self._orders.update_fields(order_id, {"status": new_status})
            await self._history.add(
                order_id=order_id,
                old_status=order.status,
                new_status=new_status,
                source=source,
                email_log_id=email_log_id,
            )
            return "advanced"

    async def _commission_per_kg(self) -> Decimal:
        raw = await self._app_settings.get("commission.per_kg_usd")
        return rules.COMMISSION_PER_KG_USD if raw is None else Decimal(str(raw))

    async def _get_locked(self, order_id: int) -> Order:
        order = await self._orders.get(order_id, for_update=True)
        if order is None:
            raise NotFoundError.entity("Заказ", order_id)
        return order


def _now() -> datetime:
    return datetime.now(UTC)
