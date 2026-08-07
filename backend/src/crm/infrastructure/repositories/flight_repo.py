from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from crm.domain.exceptions import DomainValidationError
from crm.domain.models import Flight
from crm.infrastructure.mappers.db_mappers import record_to_flight
from crm.infrastructure.repositories._sql import set_clause

_UPDATABLE = {"departed_on", "cost_usd", "description"}

_LIST_SQL = """
SELECT f.*, COALESCE(o.cnt, 0) AS orders_count
FROM flights f
LEFT JOIN LATERAL (SELECT COUNT(*) AS cnt FROM orders WHERE flight_id = f.id) o ON TRUE
"""


class PgFlightRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self, *, departed_on: date, cost_usd: Decimal, description: str | None
    ) -> Flight:
        row = await self._conn.fetchrow(
            "INSERT INTO flights (departed_on, cost_usd, description) "
            "VALUES ($1, $2, $3) RETURNING *, 0 AS orders_count",
            departed_on,
            cost_usd,
            description,
        )
        assert row is not None
        return record_to_flight(row)

    async def get(self, flight_id: int) -> Flight | None:
        row = await self._conn.fetchrow(_LIST_SQL + " WHERE f.id = $1", flight_id)
        return record_to_flight(row) if row else None

    async def list(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[Flight]:
        rows = await self._conn.fetch(
            _LIST_SQL
            + " WHERE ($1::date IS NULL OR f.departed_on >= $1)"
            + " AND ($2::date IS NULL OR f.departed_on <= $2)"
            + " ORDER BY f.departed_on DESC, f.id DESC",
            date_from,
            date_to,
        )
        return [record_to_flight(r) for r in rows]

    async def update(self, flight_id: int, fields: dict[str, Any]) -> Flight | None:
        if not fields:
            return await self.get(flight_id)
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE flights SET {clause}, updated_at = now() WHERE id = $1 RETURNING *",
                flight_id,
                *values,
            )
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        if row is None:
            return None
        return await self.get(flight_id)

    async def delete(self, flight_id: int) -> None:
        # orders.flight_id имеет ON DELETE SET NULL — заказы остаются
        await self._conn.execute("DELETE FROM flights WHERE id = $1", flight_id)
