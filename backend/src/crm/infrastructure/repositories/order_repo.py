from __future__ import annotations

from typing import Any

import asyncpg

from crm.application.interfaces.repositories import OrderFilters
from crm.domain import rules
from crm.domain.enums import OrderStatus
from crm.domain.exceptions import DomainValidationError, EntityInUseError
from crm.domain.models import Order, OrderListRow
from crm.infrastructure.mappers.db_mappers import record_to_order, record_to_order_row
from crm.infrastructure.repositories._sql import insert_clause, like_pattern, set_clause

_ACTIVE = [s.value for s in rules.ACTIVE_STATUSES]
_TERMINAL = [s.value for s in rules.TERMINAL_STATUSES]
_OVERDUE = [s.value for s in rules.OVERDUE_STATUSES]

_INSERTABLE = {
    "client_id",
    "store",
    "store_order_number",
    "items",
    "purchase_price_usd",
    "commission_usd",
    "weight_kg",
    "weight_is_final",
    "promised_date",
    "comment",
    "status",
    "refunded_amount_usd",
    "refunded_at",
    "flight_id",
    "copied_from",
    "purchased_on",
    "closed_at",
}
_UPDATABLE = _INSERTABLE

_ROW_SQL = """
SELECT o.*, c.name AS client_name,
       COALESCE(p.paid, 0) AS paid_usd,
       COALESCE(t.cnt, 0) AS tracks_count
FROM orders o
JOIN clients c ON c.id = o.client_id
LEFT JOIN LATERAL (SELECT SUM(amount_usd) AS paid FROM payments WHERE order_id = o.id) p ON TRUE
LEFT JOIN LATERAL (SELECT COUNT(*) AS cnt FROM tracks WHERE order_id = o.id) t ON TRUE
"""


class PgOrderRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(self, fields: dict[str, Any]) -> Order:
        cols, placeholders, values = insert_clause(fields, _INSERTABLE)
        try:
            row = await self._conn.fetchrow(
                f"INSERT INTO orders ({cols}) VALUES ({placeholders}) RETURNING *", *values
            )
        except asyncpg.ForeignKeyViolationError as exc:
            raise DomainValidationError("Клиент или рейс не найден") from exc
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        assert row is not None
        return record_to_order(row)

    async def get(self, order_id: int, *, for_update: bool = False) -> Order | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = await self._conn.fetchrow(
            f"SELECT * FROM orders WHERE id = $1{suffix}", order_id
        )
        return record_to_order(row) if row else None

    async def get_row(self, order_id: int) -> OrderListRow | None:
        row = await self._conn.fetchrow(_ROW_SQL + " WHERE o.id = $1", order_id)
        return record_to_order_row(row) if row else None

    async def list(self, filters: OrderFilters) -> list[OrderListRow]:
        conds: list[str] = []
        params: list[Any] = []

        def arg(value: Any) -> str:
            params.append(value)
            return f"${len(params)}"

        if filters.status is not None:
            conds.append(f"o.status = {arg(filters.status.value)}")
        if filters.client_id is not None:
            conds.append(f"o.client_id = {arg(filters.client_id)}")
        if filters.active is True:
            conds.append(f"o.status = ANY({arg(_ACTIVE)}::text[])")
        elif filters.active is False:
            conds.append(f"o.status = ANY({arg(_TERMINAL)}::text[])")
        if filters.overdue:
            conds.append(
                "o.promised_date IS NOT NULL "
                "AND o.promised_date < (now() AT TIME ZONE 'Europe/Moscow')::date "
                f"AND o.status = ANY({arg(_OVERDUE)}::text[])"
            )
        if filters.no_commission:
            conds.append(
                f"o.commission_usd IS NULL AND o.status = ANY({arg(_ACTIVE)}::text[])"
            )
        if filters.flight_id is not None:
            conds.append(f"o.flight_id = {arg(filters.flight_id)}")
        if filters.search and filters.search.strip():
            pattern = arg(like_pattern(filters.search))
            conds.append(
                f"(lower(o.items) LIKE {pattern} OR lower(o.store) LIKE {pattern} "
                f"OR lower(coalesce(o.store_order_number, '')) LIKE {pattern} "
                f"OR lower(c.name) LIKE {pattern} "
                f"OR EXISTS (SELECT 1 FROM tracks tr WHERE tr.order_id = o.id "
                f"AND lower(tr.tracking_number) LIKE {pattern}) "
                f"OR EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.id "
                f"AND (lower(coalesce(oi.title, '')) LIKE {pattern} "
                f"OR lower(coalesce(oi.url, '')) LIKE {pattern})))"
            )

        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        rows = await self._conn.fetch(
            _ROW_SQL + where + " ORDER BY lower(c.name), o.created_at DESC LIMIT 1000"
        , *params)
        return [record_to_order_row(r) for r in rows]

    async def update_fields(self, order_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            await self._conn.execute(
                f"UPDATE orders SET {clause}, updated_at = now() WHERE id = $1",
                order_id,
                *values,
            )
        except asyncpg.ForeignKeyViolationError as exc:
            raise DomainValidationError("Клиент или рейс не найден") from exc
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc

    async def delete(self, order_id: int) -> None:
        try:
            await self._conn.execute("DELETE FROM orders WHERE id = $1", order_id)
        except asyncpg.ForeignKeyViolationError as exc:
            raise EntityInUseError(
                "У заказа есть платежи — сначала удалите их или отмените заказ"
            ) from exc

    async def candidates_for_matching(
        self, *, statuses: list[OrderStatus], max_age_days: int
    ) -> list[OrderListRow]:
        rows = await self._conn.fetch(
            _ROW_SQL
            + " WHERE o.status = ANY($1::text[])"
            + " AND o.purchased_on >= (now() AT TIME ZONE 'Europe/Moscow')::date - $2::int"
            + " ORDER BY o.purchased_on DESC LIMIT 200",
            [s.value for s in statuses],
            max_age_days,
        )
        return [record_to_order_row(r) for r in rows]
