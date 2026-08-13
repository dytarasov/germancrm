from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from crm.application.interfaces.repositories import (
    OrderRepository,
    SuborderRepository,
    TrackRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.application.services.matching import MatchCandidate, MatcherService
from crm.domain.enums import OrderStatus, TrackMatchStatus, TrackSource
from crm.domain.exceptions import DomainValidationError, NotFoundError
from crm.domain.models import Track

_NORM_RE = re.compile(r"[^0-9A-Za-z]+")


def normalize_tracking_number(value: str) -> str:
    """Каноничная форма трека: только буквы и цифры, верхний регистр
    (правило то же, что у normalize_number для номеров заказов).

    Единая для ручного ввода, авто-контура и ручного разбора писем —
    иначе один трек существовал бы в БД в двух написаниях."""
    return _NORM_RE.sub("", value).upper()


class TrackService:
    def __init__(
        self,
        tracks: TrackRepository,
        orders: OrderRepository,
        suborders: SuborderRepository,
        matcher: MatcherService,
        uow: UnitOfWork,
    ) -> None:
        self._tracks = tracks
        self._orders = orders
        self._suborders = suborders
        self._matcher = matcher
        self._uow = uow

    async def _lone_active_suborder(self, order_id: int) -> int | None:
        """Подзаказ, к которому можно отнести трек без догадок, — если он один."""
        active = [
            s
            for s in await self._suborders.list_for_order(order_id)
            if s.status != OrderStatus.CANCELLED
        ]
        return active[0].id if len(active) == 1 else None

    async def create(
        self,
        *,
        tracking_number: str,
        carrier: str | None = None,
        order_id: int | None = None,
        note: str | None = None,
    ) -> Track:
        number = normalize_tracking_number(tracking_number)
        if not number:
            raise DomainValidationError("Пустой трек-номер")
        async with self._uow:
            if order_id is not None and await self._orders.get(order_id) is None:
                raise NotFoundError.entity("Заказ", order_id)
            return await self._tracks.add(
                tracking_number=number,
                carrier=carrier,
                order_id=order_id,
                suborder_id=(
                    await self._lone_active_suborder(order_id)
                    if order_id is not None
                    else None
                ),
                source=TrackSource.MANUAL,
                email_log_id=None,
                match_status=(
                    TrackMatchStatus.LINKED if order_id is not None else TrackMatchStatus.OPEN
                ),
                candidates=None,
                note=note,
            )

    async def list(
        self, *, unmatched: bool | None = None, search: str | None = None
    ) -> list[Track]:
        return await self._tracks.list(unmatched=unmatched, search=search)

    async def assign(self, track_id: int, order_id: int | None) -> Track:
        async with self._uow:
            track = await self._get(track_id)
            if order_id is not None:
                if await self._orders.get(order_id) is None:
                    raise NotFoundError.entity("Заказ", order_id)
                # suborder_id обязателен к пересчёту: иначе трек, перевешенный
                # на другой заказ, продолжил бы двигать подзаказ прежнего
                fields: dict[str, Any] = {
                    "order_id": order_id,
                    "suborder_id": await self._lone_active_suborder(order_id),
                    "match_status": TrackMatchStatus.LINKED,
                    "resolved_at": datetime.now(UTC),
                    "candidates": None,
                }
            else:
                fields = {
                    "order_id": None,
                    "suborder_id": None,
                    "match_status": TrackMatchStatus.OPEN,
                    "resolved_at": None,
                }
            updated = await self._tracks.update(track.id, fields)
            assert updated is not None
            return updated

    async def dismiss(self, track_id: int) -> Track:
        async with self._uow:
            await self._get(track_id)
            updated = await self._tracks.update(
                track_id,
                {"match_status": TrackMatchStatus.DISMISSED, "resolved_at": datetime.now(UTC)},
            )
            assert updated is not None
            return updated

    async def update(self, track_id: int, fields: dict[str, Any]) -> Track:
        if "tracking_number" in fields and fields["tracking_number"]:
            fields["tracking_number"] = normalize_tracking_number(fields["tracking_number"])
        async with self._uow:
            track = await self._tracks.update(track_id, fields)
        if track is None:
            raise NotFoundError.entity("Трек", track_id)
        return track

    async def delete(self, track_id: int) -> None:
        async with self._uow:
            await self._get(track_id)
            await self._tracks.delete(track_id)

    async def suggestions(self, track_id: int) -> list[MatchCandidate]:
        await self._get(track_id)
        candidates = await self._orders.candidates_for_matching(
            statuses=[OrderStatus.PURCHASED, OrderStatus.SHIPPED], max_age_days=60
        )
        return self._matcher.score_orders(candidates)[:10]

    async def _get(self, track_id: int) -> Track:
        track = await self._tracks.get(track_id)
        if track is None:
            raise NotFoundError.entity("Трек", track_id)
        return track
