from __future__ import annotations

from decimal import Decimal
from typing import Any

import asyncpg

from crm.domain import rules
from crm.domain.exceptions import DomainValidationError, EntityInUseError
from crm.domain.models import Client, ClientListItem, ClientStats
from crm.infrastructure.mappers.db_mappers import record_to_client
from crm.infrastructure.repositories._sql import like_pattern, set_clause

_ACTIVE = [s.value for s in rules.ACTIVE_STATUSES]
_EXCLUDED_FROM_DEBT = ["cancelled", "refunded"]
_UPDATABLE = {"name", "contacts", "telegram_url", "note"}

_LIST_SQL = """
SELECT c.*, COALESCE(s.active_orders, 0) AS active_orders, COALESCE(s.debt, 0) AS debt_usd
FROM clients c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE o.status = ANY($1::text[])) AS active_orders,
        SUM(o.purchase_price_usd + o.commission_usd - COALESCE(p.paid, 0))
            FILTER (WHERE o.status <> ALL($2::text[]) AND o.commission_usd IS NOT NULL) AS debt
    FROM orders o
    LEFT JOIN LATERAL (
        SELECT SUM(amount_usd) AS paid FROM payments WHERE order_id = o.id
    ) p ON TRUE
    WHERE o.client_id = c.id
) s ON TRUE
WHERE $3::text IS NULL
   OR lower(c.name) LIKE $3
   OR lower(coalesce(c.telegram_url, '')) LIKE $3
   OR lower(coalesce(c.contacts, '')) LIKE $3
ORDER BY lower(c.name)
LIMIT 1000
"""

_STATS_SQL = """
SELECT
    COALESCE(SUM(o.purchase_price_usd + o.commission_usd - COALESCE(p.paid, 0))
        FILTER (WHERE o.status <> ALL($2::text[]) AND o.commission_usd IS NOT NULL), 0) AS debt,
    COALESCE(SUM(o.commission_usd)
        FILTER (WHERE o.closed_at IS NOT NULL OR o.refunded_at IS NOT NULL), 0) AS earned,
    COUNT(*) FILTER (WHERE o.status = ANY($3::text[])) AS active_orders
FROM orders o
LEFT JOIN LATERAL (SELECT SUM(amount_usd) AS paid FROM payments WHERE order_id = o.id) p ON TRUE
WHERE o.client_id = $1
"""


class PgClientRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self, *, name: str, contacts: str | None, telegram_url: str | None, note: str | None
    ) -> Client:
        row = await self._conn.fetchrow(
            "INSERT INTO clients (name, contacts, telegram_url, note) "
            "VALUES ($1, $2, $3, $4) RETURNING *",
            name,
            contacts,
            telegram_url,
            note,
        )
        assert row is not None
        return record_to_client(row)

    async def get(self, client_id: int) -> Client | None:
        row = await self._conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
        return record_to_client(row) if row else None

    async def list(self, search: str | None = None) -> list[ClientListItem]:
        pattern = like_pattern(search) if search and search.strip() else None
        rows = await self._conn.fetch(_LIST_SQL, _ACTIVE, _EXCLUDED_FROM_DEBT, pattern)
        return [
            ClientListItem(
                client=record_to_client(r),
                active_orders=r["active_orders"],
                debt_usd=r["debt_usd"] or Decimal("0"),
            )
            for r in rows
        ]

    async def update(self, client_id: int, fields: dict[str, Any]) -> Client | None:
        if not fields:
            return await self.get(client_id)
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE clients SET {clause}, updated_at = now() WHERE id = $1 RETURNING *",
                client_id,
                *values,
            )
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        return record_to_client(row) if row else None

    async def delete(self, client_id: int) -> None:
        try:
            await self._conn.execute("DELETE FROM clients WHERE id = $1", client_id)
        except asyncpg.ForeignKeyViolationError as exc:
            raise EntityInUseError("У клиента есть заказы — удалить нельзя") from exc

    async def stats(self, client_id: int) -> ClientStats:
        row = await self._conn.fetchrow(_STATS_SQL, client_id, _EXCLUDED_FROM_DEBT, _ACTIVE)
        assert row is not None
        return ClientStats(
            debt_usd=row["debt"] or Decimal("0"),
            earned_usd=row["earned"] or Decimal("0"),
            active_orders=row["active_orders"],
        )
