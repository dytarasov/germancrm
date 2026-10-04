from __future__ import annotations

import logging
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
    SuborderRepository,
    TrackRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.application.services.settings_service import SettingsService, extract_domain
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
    Suborder,
    Track,
)

log = logging.getLogger("crm.orders")

AutoAdvanceOutcome = Literal[
    "advanced", "stale", "terminal", "rejected", "not_found", "ambiguous"
]

MAX_SUBORDERS = 20


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
    suborders: list[Suborder]

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
        suborders: SuborderRepository,
        uow: UnitOfWork,
        settings_service: SettingsService | None = None,
    ) -> None:
        self._orders = orders
        self._items = items
        self._tracks = tracks
        self._payments = payments
        self._history = history
        self._app_settings = app_settings
        self._suborders = suborders
        self._uow = uow
        self._settings_service = settings_service

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
            suborders=await self._suborders.list_for_order(order_id),
        )

    async def list(self, filters: OrderFilters) -> list[OrderListRow]:
        return await self._orders.list(filters)

    # ---------- создание / правка ----------

    async def create(self, fields: dict[str, Any]) -> OrderDetail:
        fields = dict(fields)
        links = [str(u).strip() for u in (fields.pop("links", None) or []) if str(u).strip()]
        # Подзаказы: список {store_order_number, amount_usd}. Одиночный
        # store_order_number (старый API) превращается в единственный подзаказ.
        specs = list(fields.pop("suborders", None) or [])
        compat_number = fields.pop("store_order_number", None)
        if not specs:
            specs = [{"store_order_number": compat_number, "amount_usd": None}]
        if len(specs) > MAX_SUBORDERS:
            raise DomainValidationError(f"Слишком много подзаказов (максимум {MAX_SUBORDERS})")
        fields.setdefault("status", OrderStatus.PURCHASED)
        fields.setdefault("purchased_on", business_today())
        async with self._uow:
            order = await self._orders.add(fields)
            for spec in specs:
                await self._suborders.add(
                    order_id=order.id,
                    store_order_number=_clean_number(spec.get("store_order_number")),
                    amount_usd=spec.get("amount_usd"),
                )
            for url in links:
                await self._items.add(order_id=order.id, title=None, url=url)
            await self._history.add(
                order_id=order.id,
                old_status=None,
                new_status=OrderStatus.PURCHASED,
                source=StatusSource.MANUAL,
            )
        log.info(
            "Создан заказ #%s (клиент %s, магазин %s, $%s)",
            order.id, order.client_id, order.store, order.purchase_price_usd,
        )
        await self._sync_store_whitelist(order.store)
        return await self.get_detail(order.id)

    async def update(self, order_id: int, fields: dict[str, Any]) -> OrderDetail:
        if not fields:
            return await self.get_detail(order_id)
        fields = dict(fields)
        async with self._uow:
            order = await self._orders.get(order_id, for_update=True)
            if order is None:
                raise NotFoundError.entity("Заказ", order_id)
            # Совместимость старого API: номер заказа магазина живёт в подзаказе.
            if "store_order_number" in fields:
                number = fields.pop("store_order_number")
                subs = await self._suborders.list_for_order(order_id)
                # цель однозначна, если подзаказ один или активный ровно один
                active = [s for s in subs if s.status != OrderStatus.CANCELLED]
                target = subs[0] if len(subs) == 1 else (active[0] if len(active) == 1 else None)
                if target is None:
                    raise DomainValidationError(
                        "У заказа несколько подзаказов — номер правится в подзаказе"
                    )
                await self._suborders.update(
                    target.id, {"store_order_number": _clean_number(number)}
                )
                # дальше сработает update_fields(fields) — на пустом dict он no-op
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
                log.info(
                    "Заказ #%s: комиссия $%s рассчитана от веса %s кг",
                    order_id, fields["commission_usd"], fields["weight_kg"],
                )
            await self._orders.update_fields(order_id, fields)
        if isinstance(fields.get("store"), str):
            await self._sync_store_whitelist(fields["store"])
        return await self.get_detail(order_id)

    async def _sync_store_whitelist(self, store: str) -> None:
        """Магазин, записанный доменом, попадает в белый список почты сам —
        письма нового магазина не отфильтруются, а старые вернутся в очередь.

        Вне транзакции заказа и в try/except: проблема с настройками почты
        не должна мешать созданию заказа."""
        if self._settings_service is None:
            return
        domain = extract_domain(store)
        if domain is None:
            return
        try:
            if await self._settings_service.ensure_whitelist_domain(domain):
                log.info("Магазин %s добавлен в белый список почты", domain)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось добавить %s в белый список почты", domain)

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
        log.info("Удалён заказ #%s (треки возвращены в очередь)", order_id)

    # ---------- статусы (руками) ----------

    async def set_status(
        self, order_id: int, new_status: OrderStatus, *, comment: str | None = None
    ) -> OrderDetail:
        """Ручная смена по линейке (в любую сторону). cancel/refund — отдельными операциями."""
        if new_status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            raise DomainValidationError("Для отмены и возврата используйте отдельные операции")
        async with self._uow:
            order = await self._get_locked(order_id)
            await self._set_status_locked(order, new_status, comment=comment)
        return await self.get_detail(order_id)

    async def _set_status_locked(
        self,
        order: Order,
        new_status: OrderStatus,
        *,
        comment: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        """Тело ручной смены статуса; заказ уже заблокирован вызывающим."""
        fields: dict[str, Any] = dict(extra_fields or {})
        if order.status == new_status:
            if fields:
                await self._orders.update_fields(order.id, fields)
            return
        fields["status"] = new_status
        if new_status == OrderStatus.CLOSED:
            rules.ensure_closable(order.commission_usd)
            fields["closed_at"] = _now()
        if order.status == OrderStatus.CLOSED and new_status != OrderStatus.CLOSED:
            fields["closed_at"] = None
        if order.status == OrderStatus.REFUNDED:
            fields["refunded_at"] = None
        await self._orders.update_fields(order.id, fields)
        # Ручной статус по линейке каскадится в подзаказы: заказ целиком
        # «уехал рейсом» и т.п. Отменённые подзаказы не трогаем, кроме
        # реактивации отменённого заказа целиком.
        if new_status in rules.ACTIVE_STATUSES:
            reactivating = order.status == OrderStatus.CANCELLED
            for sub in await self._suborders.list_for_order(order.id):
                if sub.status == new_status:
                    continue
                if sub.status == OrderStatus.CANCELLED and not reactivating:
                    continue
                await self._suborders.update(sub.id, {"status": new_status})
        await self._history.add(
            order_id=order.id,
            old_status=order.status,
            new_status=new_status,
            source=StatusSource.MANUAL,
            comment=comment,
        )
        log.info(
            "Заказ #%s: статус %s → %s (вручную)",
            order.id, order.status.value, new_status.value,
        )

    # ---------- рейсы ----------

    async def assign_flight(
        self, flight_id: int, *, add: list[int], remove: list[int], comment: str | None = None
    ) -> None:
        """Пакетное распределение по рейсу из экрана рейсов.

        add: заказ «Получено в США» → привязан к рейсу и переведён в «Рейс»;
        уже едущий/доставленный/закрытый — только перепривязывается, статус
        не меняется (так работает и откат снятия с рейса).
        remove: отвязка от этого рейса; «Рейс» откатывается в «Получено в США»,
        более поздние статусы (доставлен/закрыт) не трогаем."""
        relink_only = (OrderStatus.IN_FLIGHT, OrderStatus.DELIVERED, OrderStatus.CLOSED)
        # единый порядок блокировок — по id, чтобы параллельные пакеты не дедлочились
        ids = sorted(set(add) | set(remove))
        add_set = set(add)
        async with self._uow:
            for order_id in ids:
                order = await self._get_locked(order_id)
                if order_id in add_set:
                    if order.status in relink_only:
                        await self._orders.update_fields(order_id, {"flight_id": flight_id})
                        continue
                    if order.status != OrderStatus.AT_WAREHOUSE:
                        raise DomainValidationError(
                            f"Заказ #{order_id} нельзя отправить рейсом: "
                            "он ещё не получен в США или отменён"
                        )
                    await self._set_status_locked(
                        order,
                        OrderStatus.IN_FLIGHT,
                        comment=comment,
                        extra_fields={"flight_id": flight_id},
                    )
                elif order.flight_id == flight_id:
                    if order.status == OrderStatus.IN_FLIGHT:
                        await self._set_status_locked(
                            order,
                            OrderStatus.AT_WAREHOUSE,
                            comment="снят с рейса",
                            extra_fields={"flight_id": None},
                        )
                    else:
                        await self._orders.update_fields(order_id, {"flight_id": None})
        log.info(
            "Рейс #%s: привязаны %s, сняты %s",
            flight_id, sorted(add_set), sorted(set(remove) - add_set),
        )

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
                for sub in await self._suborders.list_for_order(order_id):
                    if sub.status != OrderStatus.CANCELLED:
                        await self._suborders.update(
                            sub.id, {"status": OrderStatus.CANCELLED}
                        )
                await self._history.add(
                    order_id=order_id,
                    old_status=order.status,
                    new_status=OrderStatus.CANCELLED,
                    source=StatusSource.MANUAL,
                    comment=comment,
                )
                log.info("Заказ #%s отменён (был %s)", order_id, order.status.value)
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
                if commission_usd is None:
                    # NULL-комиссия выкинула бы возврат из отчёта прибыли
                    # (_PERIOD_COND требует commission_usd IS NOT NULL)
                    raise DomainValidationError(
                        "Комиссию нельзя стереть: укажите сумму (можно 0) или не передавайте поле"
                    )
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
                log.info(
                    "Заказ #%s: возврат $%s (был %s)",
                    order_id, refunded_amount_usd, order.status.value,
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
            # перезаказ получит новые номера магазина — один пустой подзаказ
            await self._suborders.add(
                order_id=new_order.id, store_order_number=None, amount_usd=None
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

    # ---------- подзаказы ----------

    async def add_suborder(
        self,
        order_id: int,
        *,
        store_order_number: str | None = None,
        amount_usd: Decimal | None = None,
    ) -> Suborder:
        async with self._uow:
            order = await self._get_locked(order_id)
            self._ensure_suborders_editable(order)
            subs = await self._suborders.list_for_order(order_id)
            if len(subs) >= MAX_SUBORDERS:
                raise DomainValidationError(
                    f"Слишком много подзаказов (максимум {MAX_SUBORDERS})"
                )
            sub = await self._suborders.add(
                order_id=order_id,
                store_order_number=_clean_number(store_order_number),
                amount_usd=amount_usd,
            )
            # новый подзаказ стартует с purchased — агрегат может откатиться
            await self._recompute_order_status(order)
            return sub

    async def update_suborder(
        self, order_id: int, suborder_id: int, fields: dict[str, Any]
    ) -> Suborder:
        """Номер и справочная сумма; статус — через set_suborder_status."""
        fields = dict(fields)
        fields.pop("status", None)
        if "store_order_number" in fields:
            fields["store_order_number"] = _clean_number(fields["store_order_number"])
        async with self._uow:
            order = await self._get_locked(order_id)
            self._ensure_suborders_editable(order)
            await self._get_suborder(order_id, suborder_id)
            updated = await self._suborders.update(suborder_id, fields)
            assert updated is not None
            return updated

    async def delete_suborder(self, order_id: int, suborder_id: int) -> None:
        async with self._uow:
            order = await self._get_locked(order_id)
            self._ensure_suborders_editable(order)
            sub = await self._get_suborder(order_id, suborder_id)
            subs = await self._suborders.list_for_order(order_id)
            if len(subs) <= 1:
                raise DomainValidationError("Нельзя удалить единственный подзаказ")
            # Удаление последнего активного молча отменило бы весь заказ
            # через агрегат — отмена должна быть явной операцией.
            rest_active = [
                s
                for s in subs
                if s.id != suborder_id and s.status != OrderStatus.CANCELLED
            ]
            if sub.status != OrderStatus.CANCELLED and not rest_active:
                raise DomainValidationError(
                    "Это последний активный подзаказ — отмените заказ целиком"
                )
            # треки подзаказа остаются на заказе (suborder_id обнулится по FK)
            await self._suborders.delete(suborder_id)
            await self._recompute_order_status(order)
        log.info("Заказ #%s: удалён подзаказ #%s", order_id, suborder_id)

    @staticmethod
    def _ensure_suborders_editable(order: Order) -> None:
        """Состав подзаказов правится только у живого заказа.

        У закрытого/возвращённого это ломало бы отчётность, у отменённого —
        молча воскрешало бы заказ через агрегатный статус, без следа в истории.
        Для отменённого сначала «Вернуть в работу» (там пишется история)."""
        if order.status in rules.TERMINAL_STATUSES:
            raise DomainValidationError(
                "Заказ закрыт, отменён или возвращён — сначала верните его в работу"
            )

    async def set_suborder_status(
        self,
        order_id: int,
        suborder_id: int,
        new_status: OrderStatus,
        *,
        comment: str | None = None,
    ) -> OrderDetail:
        if new_status not in rules.SUBORDER_STATUSES:
            raise DomainValidationError("Недопустимый статус подзаказа")
        async with self._uow:
            order = await self._get_locked(order_id)
            self._ensure_suborders_editable(order)
            sub = await self._get_suborder(order_id, suborder_id)
            if sub.status != new_status:
                await self._suborders.update(suborder_id, {"status": new_status})
                await self._history.add(
                    order_id=order_id,
                    old_status=sub.status,
                    new_status=new_status,
                    source=StatusSource.MANUAL,
                    comment=comment,
                    suborder_id=suborder_id,
                )
                await self._recompute_order_status(order)
                log.info(
                    "Заказ #%s, подзаказ #%s: статус %s → %s (вручную)",
                    order_id, suborder_id, sub.status.value, new_status.value,
                )
        return await self.get_detail(order_id)

    async def _get_suborder(self, order_id: int, suborder_id: int) -> Suborder:
        sub = await self._suborders.get(suborder_id, for_update=True)
        if sub is None or sub.order_id != order_id:
            raise NotFoundError.entity("Подзаказ", suborder_id)
        return sub

    async def _recompute_order_status(self, order: Order) -> None:
        """Агрегат заказа-корзины = худший из активных подзаказов.

        Вызывать под блокировкой заказа. История не пишется: детали смены
        зафиксированы строкой уровня подзаказа."""
        subs = await self._suborders.list_for_order(order.id)
        agg = rules.aggregate_order_status([s.status for s in subs], order.status)
        if agg != order.status:
            await self._orders.update_fields(order.id, {"status": agg})
            log.info(
                "Заказ #%s: агрегатный статус %s → %s (по подзаказам)",
                order.id, order.status.value, agg.value,
            )

    # ---------- статусы (автоматика) ----------

    async def advance_status_auto(
        self,
        order_id: int,
        new_status: OrderStatus,
        *,
        email_log_id: int,
        source: StatusSource = StatusSource.AUTO,
    ) -> AutoAdvanceOutcome:
        """Продвижение без знания подзаказа: допустимо только когда активный
        подзаказ один — иначе 'ambiguous' и решение за человеком.

        source=MANUAL — когда событие письма применяет человек из очереди разбора:
        правила безопасности те же, но в истории виден настоящий автор решения."""
        async with self._uow:
            order = await self._orders.get(order_id, for_update=True)
            if order is None:
                return "not_found"
            if order.status in rules.TERMINAL_STATUSES:
                return "terminal"
            subs = await self._suborders.list_for_order(order_id)
            active = [s for s in subs if s.status != OrderStatus.CANCELLED]
            if not active:
                return "terminal"
            if len(active) > 1:
                return "ambiguous"
            return await self._advance_suborder_locked(
                order, active[0], new_status, email_log_id=email_log_id, source=source
            )

    async def advance_suborder_auto(
        self,
        suborder_id: int,
        new_status: OrderStatus,
        *,
        email_log_id: int,
        source: StatusSource = StatusSource.AUTO,
    ) -> AutoAdvanceOutcome:
        """Продвижение конкретного подзаказа (номер заказа магазина совпал)."""
        async with self._uow:
            peek = await self._suborders.get(suborder_id)
            if peek is None:
                return "not_found"
            # порядок блокировок как везде: сначала заказ, потом подзаказ
            order = await self._orders.get(peek.order_id, for_update=True)
            if order is None:
                return "not_found"
            sub = await self._suborders.get(suborder_id, for_update=True)
            if sub is None:
                return "not_found"
            if (
                order.status in (OrderStatus.CLOSED, OrderStatus.REFUNDED)
                or sub.status == OrderStatus.CANCELLED
            ):
                return "terminal"
            return await self._advance_suborder_locked(
                order, sub, new_status, email_log_id=email_log_id, source=source
            )

    async def _advance_suborder_locked(
        self,
        order: Order,
        sub: Suborder,
        new_status: OrderStatus,
        *,
        email_log_id: int,
        source: StatusSource,
    ) -> AutoAdvanceOutcome:
        """Только вперёд, только shipped/at_warehouse. Заказ и подзаказ заблокированы."""
        if new_status not in rules.AUTO_TARGETS:
            return "rejected"
        if rules.flow_index(new_status) <= rules.flow_index(sub.status):
            return "stale"
        await self._suborders.update(sub.id, {"status": new_status})
        await self._history.add(
            order_id=order.id,
            old_status=sub.status,
            new_status=new_status,
            source=source,
            email_log_id=email_log_id,
            suborder_id=sub.id,
        )
        await self._recompute_order_status(order)
        log.info(
            "Заказ #%s, подзаказ #%s: статус %s → %s (%s, письмо #%s)",
            order.id, sub.id, sub.status.value, new_status.value, source.value, email_log_id,
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


def _clean_number(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None
