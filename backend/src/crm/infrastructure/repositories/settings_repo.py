from __future__ import annotations

from typing import Any

import asyncpg


class PgSettingsRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def all(self) -> dict[str, Any]:
        rows = await self._conn.fetch("SELECT key, value FROM app_settings")
        return {r["key"]: r["value"] for r in rows}

    async def get(self, key: str) -> Any | None:
        return await self._conn.fetchval("SELECT value FROM app_settings WHERE key = $1", key)

    async def set_many(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            await self._conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ($1, $2) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                key,
                value,
            )
