from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from crm.domain.exceptions import DomainValidationError
from crm.domain.models import Payment
from crm.infrastructure.mappers.db_mappers import record_to_payment
from crm.infrastructure.repositories._sql import set_clause

_UPDATABLE = {"paid_on", "amount_usd", "comment"}


class PgPaymentRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self, *, order_id: int, paid_on: date, amount_usd: Decimal, comment: str | None
    ) -> Payment:
        row = await self._conn.fetchrow(
            "INSERT INTO payments (order_id, paid_on, amount_usd, comment) "
            "VALUES ($1, $2, $3, $4) RETURNING *",
            order_id,
            paid_on,
            amount_usd,
            comment,
        )
        assert row is not None
        return record_to_payment(row)

    async def get(self, payment_id: int) -> Payment | None:
        row = await self._conn.fetchrow("SELECT * FROM payments WHERE id = $1", payment_id)
        return record_to_payment(row) if row else None

    async def list_for_order(self, order_id: int) -> list[Payment]:
        rows = await self._conn.fetch(
            "SELECT * FROM payments WHERE order_id = $1 ORDER BY paid_on, id", order_id
        )
        return [record_to_payment(r) for r in rows]

    async def list(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        client_id: int | None = None,
    ) -> list[Payment]:
        rows = await self._conn.fetch(
            "SELECT p.* FROM payments p JOIN orders o ON o.id = p.order_id "
            "WHERE ($1::date IS NULL OR p.paid_on >= $1) "
            "AND ($2::date IS NULL OR p.paid_on <= $2) "
            "AND ($3::bigint IS NULL OR o.client_id = $3) "
            "ORDER BY p.paid_on DESC, p.id DESC",
            date_from,
            date_to,
            client_id,
        )
        return [record_to_payment(r) for r in rows]

    async def update(self, payment_id: int, fields: dict[str, Any]) -> Payment | None:
        if not fields:
            return await self.get(payment_id)
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE payments SET {clause} WHERE id = $1 RETURNING *", payment_id, *values
            )
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        return record_to_payment(row) if row else None

    async def delete(self, payment_id: int) -> None:
        await self._conn.execute("DELETE FROM payments WHERE id = $1", payment_id)

    async def sum_for_order(self, order_id: int) -> Decimal:
        value = await self._conn.fetchval(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM payments WHERE order_id = $1", order_id
        )
        return value or Decimal("0")
