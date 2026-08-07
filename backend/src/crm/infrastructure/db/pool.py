from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

log = logging.getLogger("crm.db")

# Ошибки «БД ещё не готова» — их пережидаем: нет DNS-имени или коннекта
# (OSError покрывает gaierror и ConnectionRefused — контейнер postgres ещё
# не поднялся), постгрес стартует (CannotConnectNow), обрыв рукопожатия.
# Ошибки конфигурации (неверный пароль, нет такой БД) НЕ ретраятся — fail fast.
_TRANSIENT = (
    OSError,
    TimeoutError,
    asyncpg.exceptions.CannotConnectNowError,
    asyncpg.exceptions.PostgresConnectionError,
)


async def _init_connection(conn: asyncpg.Connection) -> None:
    # jsonb/json <-> dict/list прозрачно для всего приложения
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_pool(
    dsn: str, *, min_size: int = 1, max_size: int = 10, retry_for: float = 90.0
) -> asyncpg.Pool:
    """Создаёт пул, терпеливо пережидая старт БД.

    После перезагрузки сервера docker поднимает контейнеры в произвольном
    порядке (restart-политика не знает про depends_on), а DNS-имя остановленного
    контейнера не резолвится вовсе — бэкенд обязан подождать БД, а не падать
    в краш-луп с gaierror.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + retry_for
    delay = 0.5
    while True:
        try:
            pool = await asyncpg.create_pool(
                dsn, min_size=min_size, max_size=max_size, init=_init_connection
            )
            assert pool is not None
            return pool
        except _TRANSIENT as exc:
            if loop.time() >= deadline:
                log.error("БД так и не поднялась за %.0f с — сдаюсь", retry_for)
                raise
            log.warning(
                "БД недоступна (%s: %s) — повтор через %.1f с",
                exc.__class__.__name__,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 5.0)
