from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from crm.domain.models import GmailCredentials, GmailSyncState
from crm.infrastructure.mappers.db_mappers import (
    record_to_gmail_credentials,
    record_to_gmail_sync_state,
)
from crm.infrastructure.repositories._sql import set_clause

_SYNC_UPDATABLE = {
    "history_id",
    "last_poll_at",
    "last_success_at",
    "last_error",
    "consecutive_failures",
    "llm_degraded",
}


class PgGmailStateRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def get_credentials(self) -> GmailCredentials | None:
        row = await self._conn.fetchrow("SELECT * FROM gmail_credentials WHERE id = 1")
        return record_to_gmail_credentials(row) if row else None

    async def save_credentials(
        self,
        *,
        email_address: str | None,
        refresh_token: str,
        access_token: str | None,
        expires_at: datetime | None,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO gmail_credentials
                (id, email_address, refresh_token, access_token, access_token_expires_at)
            VALUES (1, $1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                email_address = EXCLUDED.email_address,
                refresh_token = EXCLUDED.refresh_token,
                access_token = EXCLUDED.access_token,
                access_token_expires_at = EXCLUDED.access_token_expires_at,
                authorized_at = now(),
                revoked_at = NULL,
                updated_at = now()
            """,
            email_address,
            refresh_token,
            access_token,
            expires_at,
        )

    async def update_access_token(self, access_token: str, expires_at: datetime) -> None:
        await self._conn.execute(
            "UPDATE gmail_credentials SET access_token = $1, access_token_expires_at = $2, "
            "updated_at = now() WHERE id = 1",
            access_token,
            expires_at,
        )

    async def mark_revoked(self) -> None:
        await self._conn.execute(
            "UPDATE gmail_credentials SET revoked_at = now(), updated_at = now() WHERE id = 1"
        )

    async def get_sync_state(self) -> GmailSyncState:
        row = await self._conn.fetchrow("SELECT * FROM gmail_sync_state WHERE id = 1")
        if row is None:
            await self._conn.execute(
                "INSERT INTO gmail_sync_state (id) VALUES (1) ON CONFLICT DO NOTHING"
            )
            row = await self._conn.fetchrow("SELECT * FROM gmail_sync_state WHERE id = 1")
        assert row is not None
        return record_to_gmail_sync_state(row)

    async def update_sync_state(self, fields: dict[str, Any]) -> None:
        if not fields:
            return
        clause, values = set_clause(fields, _SYNC_UPDATABLE)
        await self._conn.execute(
            f"UPDATE gmail_sync_state SET {clause}, updated_at = now() WHERE id = 1", *values
        )
