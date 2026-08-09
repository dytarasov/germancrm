"""Баны по IP за перебор пароля: 5 промахов подряд — блок на 48 часов.

Счётчик копится, пока промахи идут чаще, чем раз в час; успешный вход или
снятие бана в CRM стирают запись. Приватные адреса сюда не попадают —
роутер логина отправляет их только в мягкий глобальный лимит.
"""

from __future__ import annotations

from datetime import UTC, datetime

from crm.application.interfaces.repositories import LoginBanRepository
from crm.application.interfaces.uow import UnitOfWork
from crm.domain.models import LoginBan

MAX_FAILS = 5
BAN_HOURS = 48
RESET_WINDOW_MIN = 60


class SecurityService:
    def __init__(self, bans: LoginBanRepository, uow: UnitOfWork) -> None:
        self._bans = bans
        self._uow = uow

    async def banned_until(self, ip: str) -> datetime | None:
        ban = await self._bans.get(ip)
        if ban is None or ban.banned_until is None:
            return None
        return ban.banned_until if ban.banned_until > _now() else None

    async def register_fail(self, ip: str) -> LoginBan:
        async with self._uow:
            return await self._bans.register_fail(
                ip,
                reset_window_min=RESET_WINDOW_MIN,
                max_fails=MAX_FAILS,
                ban_hours=BAN_HOURS,
            )

    async def clear(self, ip: str) -> None:
        async with self._uow:
            await self._bans.clear(ip)

    async def list_bans(self) -> list[LoginBan]:
        async with self._uow:
            return await self._bans.list_recent()

    async def unban(self, ip: str) -> None:
        async with self._uow:
            await self._bans.clear(ip)


def _now() -> datetime:
    return datetime.now(UTC)
