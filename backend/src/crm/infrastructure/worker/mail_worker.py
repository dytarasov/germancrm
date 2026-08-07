"""Фоновый воркер почты: asyncio-задача в lifespan.

Правила: никогда не роняет приложение; backoff при ошибках; advisory lock
против дублей при нескольких процессах; мгновенная остановка по stop-event;
пробуждение вне расписания по wake-event (кнопка «Проверить сейчас»)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random

import asyncpg
from dishka import AsyncContainer

from crm.application.services.mail_service import MailService

log = logging.getLogger("crm.mail.worker")

WORKER_LOCK_KEY = 0x6765726D_637202
MAX_BACKOFF_SEC = 1800


async def run_mail_worker(
    container: AsyncContainer, stop: asyncio.Event, wake: asyncio.Event
) -> None:
    log.info("Почтовый воркер запущен")
    failures = 0
    while not stop.is_set():
        interval = 180.0
        try:
            async with container() as scope:
                mail = await scope.get(MailService)
                interval = float(await mail.poll_interval_sec())
                if await mail.has_credentials():
                    conn = await scope.get(asyncpg.Connection)
                    got_lock = await conn.fetchval(
                        "SELECT pg_try_advisory_lock($1)", WORKER_LOCK_KEY
                    )
                    if got_lock:
                        try:
                            inserted = await mail.ingest_cycle()
                            stats = await mail.process_cycle()
                            refreshed = await mail.retro_match()
                            if inserted or stats.processed or stats.manual:
                                log.info(
                                    "Цикл почты: +%s писем, обработано %s, в разбор %s, "
                                    "подсказок обновлено %s",
                                    inserted,
                                    stats.processed,
                                    stats.manual,
                                    refreshed,
                                )
                        finally:
                            await conn.fetchval(
                                "SELECT pg_advisory_unlock($1)", WORKER_LOCK_KEY
                            )
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — воркер не должен умирать
            failures += 1
            log.exception("Цикл почтового воркера упал")
            with contextlib.suppress(Exception):
                async with container() as scope:
                    mail = await scope.get(MailService)
                    await mail.record_cycle_error(f"{exc.__class__.__name__}: {exc}")
            interval = min(interval * (2 ** min(failures, 4)), MAX_BACKOFF_SEC)

        delay = interval * (0.9 + random.random() * 0.2)
        await _wait_stop_wake_or_timeout(stop, wake, delay)
    log.info("Почтовый воркер остановлен")


async def _wait_stop_wake_or_timeout(
    stop: asyncio.Event, wake: asyncio.Event, timeout: float
) -> None:
    stop_task = asyncio.create_task(stop.wait())
    wake_task = asyncio.create_task(wake.wait())
    _, pending = await asyncio.wait(
        {stop_task, wake_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    wake.clear()


def log_if_crashed(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.critical("Почтовый воркер аварийно завершился: %s", exc, exc_info=exc)
