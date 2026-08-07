from __future__ import annotations

from typing import Any

import asyncpg

from crm.domain.exceptions import DomainValidationError
from crm.domain.models import OrderItem
from crm.infrastructure.repositories._sql import set_clause

_UPDATABLE = {"title", "url", "quantity", "note"}


def _record_to_item(r: asyncpg.Record) -> OrderItem:
    return OrderItem(
        id=r["id"],
        order_id=r["order_id"],
        title=r["title"],
        url=r["url"],
        quantity=r["quantity"],
        note=r["note"],
        created_at=r["created_at"],
    )


class PgOrderItemRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self,
        *,
        order_id: int,
        title: str | None,
        url: str | None,
        quantity: int = 1,
        note: str | None = None,
    ) -> OrderItem:
        try:
            row = await self._conn.fetchrow(
                "INSERT INTO order_items (order_id, title, url, quantity, note) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING *",
                order_id,
                title,
                url,
                quantity,
                note,
            )
        except asyncpg.CheckViolationError as exc:
            raise DomainValidationError("У позиции должно быть название или ссылка") from exc
        assert row is not None
        return _record_to_item(row)

    async def get(self, item_id: int) -> OrderItem | None:
        row = await self._conn.fetchrow("SELECT * FROM order_items WHERE id = $1", item_id)
        return _record_to_item(row) if row else None

    async def list_for_order(self, order_id: int) -> list[OrderItem]:
        rows = await self._conn.fetch(
            "SELECT * FROM order_items WHERE order_id = $1 ORDER BY id", order_id
        )
        return [_record_to_item(r) for r in rows]

    async def update(self, item_id: int, fields: dict[str, Any]) -> OrderItem | None:
        if not fields:
            return await self.get(item_id)
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE order_items SET {clause}, updated_at = now() "
                "WHERE id = $1 RETURNING *",
                item_id,
                *values,
            )
        except asyncpg.CheckViolationError as exc:
            raise DomainValidationError("У позиции должно быть название или ссылка") from exc
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        return _record_to_item(row) if row else None

    async def delete(self, item_id: int) -> None:
        await self._conn.execute("DELETE FROM order_items WHERE id = $1", item_id)
