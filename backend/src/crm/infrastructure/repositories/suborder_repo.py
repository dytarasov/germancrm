from __future__ import annotations

from decimal import Decimal
from typing import Any

import asyncpg

from crm.domain.enums import OrderStatus
from crm.domain.exceptions import DomainValidationError
from crm.domain.models import Suborder
from crm.infrastructure.mappers.db_mappers import record_to_suborder
from crm.infrastructure.repositories._sql import set_clause

_UPDATABLE = {"store_order_number", "amount_usd", "status"}

# Та же каноническая форма, что normalize_number в Python: только буквы/цифры, upper.
_NORM_SQL = "upper(regexp_replace(store_order_number, '[^a-zA-Z0-9]+', '', 'g'))"


class PgSuborderRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self,
        *,
        order_id: int,
        store_order_number: str | None,
        amount_usd: Decimal | None,
        status: OrderStatus = OrderStatus.PURCHASED,
    ) -> Suborder:
        try:
            row = await self._conn.fetchrow(
                "INSERT INTO suborders (order_id, store_order_number, amount_usd, status) "
                "VALUES ($1, $2, $3, $4) RETURNING *",
                order_id,
                store_order_number,
                amount_usd,
                status.value,
            )
        except asyncpg.ForeignKeyViolationError as exc:
            raise DomainValidationError("Заказ не найден") from exc
        except asyncpg.CheckViolationError as exc:
            raise DomainValidationError("Недопустимое значение подзаказа") from exc
        assert row is not None
        return record_to_suborder(row)

    async def get(self, suborder_id: int, *, for_update: bool = False) -> Suborder | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = await self._conn.fetchrow(
            f"SELECT * FROM suborders WHERE id = $1{suffix}", suborder_id
        )
        return record_to_suborder(row) if row else None

    async def list_for_order(self, order_id: int) -> list[Suborder]:
        rows = await self._conn.fetch(
            "SELECT * FROM suborders WHERE order_id = $1 ORDER BY id", order_id
        )
        return [record_to_suborder(r) for r in rows]

    async def update(self, suborder_id: int, fields: dict[str, Any]) -> Suborder | None:
        if not fields:
            return await self.get(suborder_id)
        fields = {
            k: (str(v) if k == "status" and v is not None else v) for k, v in fields.items()
        }
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE suborders SET {clause}, updated_at = now() WHERE id = $1 RETURNING *",
                suborder_id,
                *values,
            )
        except asyncpg.CheckViolationError as exc:
            raise DomainValidationError("Недопустимый статус подзаказа") from exc
        return record_to_suborder(row) if row else None

    async def delete(self, suborder_id: int) -> None:
        await self._conn.execute("DELETE FROM suborders WHERE id = $1", suborder_id)

    async def find_by_number(self, normalized_number: str) -> list[Suborder]:
        if not normalized_number:
            return []
        rows = await self._conn.fetch(
            f"SELECT * FROM suborders WHERE store_order_number IS NOT NULL "
            f"AND {_NORM_SQL} = $1 ORDER BY id",
            normalized_number,
        )
        return [record_to_suborder(r) for r in rows]
