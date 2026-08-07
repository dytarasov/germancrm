from __future__ import annotations

import asyncpg

from crm.domain.enums import OrderStatus
from crm.domain.models import StatusChange
from crm.infrastructure.mappers.db_mappers import record_to_status_change


class PgStatusHistoryRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self,
        *,
        order_id: int,
        old_status: OrderStatus | None,
        new_status: OrderStatus,
        source: str,
        email_log_id: int | None = None,
        comment: str | None = None,
    ) -> StatusChange:
        row = await self._conn.fetchrow(
            "INSERT INTO order_status_history "
            "(order_id, old_status, new_status, source, email_log_id, comment) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
            order_id,
            old_status.value if old_status else None,
            new_status.value,
            str(source),
            email_log_id,
            comment,
        )
        assert row is not None
        return record_to_status_change(row)

    async def list_for_order(self, order_id: int) -> list[StatusChange]:
        rows = await self._conn.fetch(
            "SELECT * FROM order_status_history WHERE order_id = $1 "
            "ORDER BY changed_at DESC, id DESC",
            order_id,
        )
        return [record_to_status_change(r) for r in rows]
