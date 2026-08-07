"""Старт пула БД: транзиентные ошибки пережидаются, конфигурационные — нет."""

from __future__ import annotations

import asyncpg
import pytest

from crm.infrastructure.db import pool as pool_mod


async def test_transient_errors_are_retried(monkeypatch):
    """gaierror/ConnectionRefused (нет контейнера/DNS) → ретрай до успеха."""
    calls = {"n": 0}
    sentinel = object()

    async def fake_create_pool(dsn, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("Temporary failure in name resolution")
        return sentinel

    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(pool_mod.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(pool_mod.asyncio, "sleep", fake_sleep)

    result = await pool_mod.create_pool("postgresql://x", retry_for=60)
    assert result is sentinel
    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # backoff растёт


async def test_postgres_starting_up_is_retried(monkeypatch):
    """CannotConnectNow («the database system is starting up») — тоже ждём."""
    calls = {"n": 0}
    sentinel = object()

    async def fake_create_pool(dsn, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise asyncpg.exceptions.CannotConnectNowError("starting up")
        return sentinel

    monkeypatch.setattr(pool_mod.asyncpg, "create_pool", fake_create_pool)

    async def fake_sleep(d):
        pass

    monkeypatch.setattr(pool_mod.asyncio, "sleep", fake_sleep)
    assert await pool_mod.create_pool("postgresql://x", retry_for=60) is sentinel


async def test_config_errors_fail_fast(monkeypatch):
    """Неверный пароль — не транзиентная ошибка, ретраев быть не должно."""
    calls = {"n": 0}

    async def fake_create_pool(dsn, **kwargs):
        calls["n"] += 1
        raise asyncpg.InvalidPasswordError("password authentication failed")

    monkeypatch.setattr(pool_mod.asyncpg, "create_pool", fake_create_pool)
    with pytest.raises(asyncpg.InvalidPasswordError):
        await pool_mod.create_pool("postgresql://x", retry_for=60)
    assert calls["n"] == 1


async def test_gives_up_after_deadline(monkeypatch):
    async def fake_create_pool(dsn, **kwargs):
        raise OSError("no route to host")

    monkeypatch.setattr(pool_mod.asyncpg, "create_pool", fake_create_pool)
    with pytest.raises(OSError):
        await pool_mod.create_pool("postgresql://x", retry_for=0)
