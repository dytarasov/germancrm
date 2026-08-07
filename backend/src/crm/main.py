from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from crm.application.services.auth_service import AuthService
from crm.di.container import make_container
from crm.infrastructure.config import Settings
from crm.infrastructure.db.migrations import MigrationRunner
from crm.infrastructure.worker.mail_worker import log_if_crashed, run_mail_worker
from crm.presentation.errors import register_error_handlers
from crm.presentation.routers import (
    auth,
    clients,
    dashboard,
    flights,
    health,
    mail,
    orders,
    payments,
    reports,
    search,
    tracks,
)
from crm.presentation.routers import (
    settings as settings_router,
)

log = logging.getLogger("crm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = app.state.dishka_container
    settings: Settings = app.state.settings

    pool = await container.get(asyncpg.Pool)
    await MigrationRunner(pool, settings.migrations_dir).run()

    stop = asyncio.Event()
    worker_task: asyncio.Task | None = None
    if settings.mail_worker_enabled:
        worker_task = asyncio.create_task(
            run_mail_worker(container, stop, app.state.mail_wake), name="mail-worker"
        )
        worker_task.add_done_callback(log_if_crashed)

    yield

    stop.set()
    if worker_task is not None:
        try:
            await asyncio.wait_for(worker_task, timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)
    await container.close()


_DEFAULT_SECRETS = {"admin", "change-me", "dev-secret-change-me", "change-me-long-random"}


def _check_secrets(settings: Settings) -> None:
    """Дефолтные секреты допустимы только на localhost — прод с ними не стартует."""
    insecure = (
        settings.app_password in _DEFAULT_SECRETS or settings.secret_key in _DEFAULT_SECRETS
    )
    if not insecure:
        return
    is_local = "localhost" in settings.public_base_url or "127.0.0.1" in settings.public_base_url
    if not is_local or settings.cookie_secure:
        raise RuntimeError(
            "APP_PASSWORD/SECRET_KEY остались дефолтными — задайте их в .env "
            "перед запуском не на localhost"
        )
    log.warning(
        "APP_PASSWORD/SECRET_KEY дефолтные — для localhost допустимо, "
        "но смените их в .env"
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    _check_secrets(settings)

    app = FastAPI(
        title="shaprivezu",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.auth_service = AuthService(
        password=settings.app_password,
        secret=settings.secret_key,
        ttl_days=settings.session_ttl_days,
    )
    app.state.mail_wake = asyncio.Event()
    app.state.login_fails = []  # таймстемпы неудачных логинов (rate limit)
    app.state.oauth_states = set()  # одноразовые OAuth-state

    container = make_container(settings)
    setup_dishka(container, app)

    register_error_handlers(app)

    for router in (
        auth.router,
        clients.router,
        orders.router,
        tracks.router,
        payments.router,
        flights.router,
        dashboard.router,
        reports.router,
        search.router,
        mail.router,
        settings_router.router,
        health.router,
    ):
        app.include_router(router)

    return app


app = create_app()
