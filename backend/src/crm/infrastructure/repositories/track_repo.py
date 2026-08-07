from __future__ import annotations

from typing import Any

import asyncpg

from crm.domain.exceptions import DomainValidationError, DuplicateError
from crm.domain.models import Track
from crm.infrastructure.mappers.db_mappers import record_to_track
from crm.infrastructure.repositories._sql import like_pattern, set_clause

_UPDATABLE = {
    "tracking_number",
    "carrier",
    "order_id",
    "match_status",
    "candidates",
    "note",
    "resolved_at",
}


class PgTrackRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def add(
        self,
        *,
        tracking_number: str,
        carrier: str | None,
        order_id: int | None,
        source: str,
        email_log_id: int | None,
        match_status: str,
        candidates: list[dict[str, Any]] | None,
        note: str | None,
    ) -> Track:
        try:
            row = await self._conn.fetchrow(
                "INSERT INTO tracks (tracking_number, carrier, order_id, source, "
                "email_log_id, match_status, candidates, note) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *",
                tracking_number,
                carrier,
                order_id,
                str(source),
                email_log_id,
                str(match_status),
                candidates,
                note,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateError(f"Трек {tracking_number} уже существует") from exc
        assert row is not None
        return record_to_track(row)

    async def get(self, track_id: int) -> Track | None:
        row = await self._conn.fetchrow("SELECT * FROM tracks WHERE id = $1", track_id)
        return record_to_track(row) if row else None

    async def get_by_number(self, tracking_number: str) -> Track | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM tracks WHERE tracking_number = $1", tracking_number
        )
        return record_to_track(row) if row else None

    async def list(
        self, *, unmatched: bool | None = None, search: str | None = None
    ) -> list[Track]:
        conds: list[str] = []
        params: list[Any] = []
        if unmatched is True:
            conds.append("match_status = 'open'")
        if search and search.strip():
            params.append(like_pattern(search))
            conds.append(f"lower(tracking_number) LIKE ${len(params)}")
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        rows = await self._conn.fetch(
            f"SELECT * FROM tracks{where} ORDER BY created_at DESC LIMIT 500", *params
        )
        return [record_to_track(r) for r in rows]

    async def list_for_order(self, order_id: int) -> list[Track]:
        rows = await self._conn.fetch(
            "SELECT * FROM tracks WHERE order_id = $1 ORDER BY created_at", order_id
        )
        return [record_to_track(r) for r in rows]

    async def update(self, track_id: int, fields: dict[str, Any]) -> Track | None:
        if not fields:
            return await self.get(track_id)
        fields = {k: (str(v) if k == "match_status" and v is not None else v) for k, v in fields.items()}
        clause, values = set_clause(fields, _UPDATABLE, start=2)
        try:
            row = await self._conn.fetchrow(
                f"UPDATE tracks SET {clause}, updated_at = now() WHERE id = $1 RETURNING *",
                track_id,
                *values,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateError("Трек с таким номером уже существует") from exc
        except asyncpg.NotNullViolationError as exc:
            raise DomainValidationError(f"Поле {exc.column_name} обязательно") from exc
        return record_to_track(row) if row else None

    async def delete(self, track_id: int) -> None:
        await self._conn.execute("DELETE FROM tracks WHERE id = $1", track_id)

    async def open_tracks(self) -> list[Track]:
        rows = await self._conn.fetch(
            "SELECT * FROM tracks WHERE match_status = 'open' ORDER BY created_at DESC"
        )
        return [record_to_track(r) for r in rows]
