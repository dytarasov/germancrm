from __future__ import annotations

import asyncpg

from crm.domain.models import LoginBan


def _to_model(r: asyncpg.Record) -> LoginBan:
    return LoginBan(
        ip=r["ip"],
        fails=r["fails"],
        last_fail_at=r["last_fail_at"],
        banned_until=r["banned_until"],
    )


class PgLoginBanRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def get(self, ip: str) -> LoginBan | None:
        row = await self._conn.fetchrow("SELECT * FROM login_bans WHERE ip = $1", ip)
        return _to_model(row) if row else None

    async def register_fail(
        self, ip: str, *, reset_window_min: int, max_fails: int, ban_hours: int
    ) -> LoginBan:
        # Истёкший бан не должен «дозакрываться» со старым счётчиком.
        await self._conn.execute(
            "UPDATE login_bans SET banned_until = NULL, fails = 0 "
            "WHERE ip = $1 AND banned_until IS NOT NULL AND banned_until <= now()",
            ip,
        )
        row = await self._conn.fetchrow(
            """
            INSERT INTO login_bans (ip, fails, last_fail_at)
            VALUES ($1, 1, now())
            ON CONFLICT (ip) DO UPDATE SET
                fails = CASE
                    WHEN login_bans.last_fail_at < now() - make_interval(mins => $2)
                        THEN 1
                    ELSE login_bans.fails + 1
                END,
                last_fail_at = now()
            RETURNING *
            """,
            ip,
            reset_window_min,
        )
        assert row is not None
        if row["fails"] >= max_fails and row["banned_until"] is None:
            row = await self._conn.fetchrow(
                "UPDATE login_bans SET banned_until = now() + make_interval(hours => $2) "
                "WHERE ip = $1 RETURNING *",
                ip,
                ban_hours,
            )
            assert row is not None
        return _to_model(row)

    async def clear(self, ip: str) -> None:
        await self._conn.execute("DELETE FROM login_bans WHERE ip = $1", ip)

    async def list_recent(self, limit: int = 50) -> list[LoginBan]:
        # Заодно чистим давно неактуальные строки, чтобы таблица не пухла.
        await self._conn.execute(
            "DELETE FROM login_bans WHERE last_fail_at < now() - interval '7 days' "
            "AND (banned_until IS NULL OR banned_until <= now())"
        )
        rows = await self._conn.fetch(
            "SELECT * FROM login_bans ORDER BY last_fail_at DESC LIMIT $1", limit
        )
        return [_to_model(r) for r in rows]
