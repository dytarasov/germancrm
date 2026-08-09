from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from crm.infrastructure.config import Settings
from crm.infrastructure.db.migrations import MigrationRunner
from crm.infrastructure.db.pool import create_pool
from crm.main import create_app

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://crm:crm@localhost:5433/crm_test"
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

TABLES = (
    "email_event, order_status_history, payments, tracks, email_log, "
    "orders, flights, clients, login_bans"
)


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    async def run() -> None:
        pool = await create_pool(TEST_DSN, min_size=1, max_size=2)
        try:
            await MigrationRunner(pool, MIGRATIONS_DIR).run()
        finally:
            await pool.close()

    asyncio.run(run())


@pytest_asyncio.fixture
async def pool():
    pool = await create_pool(TEST_DSN, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def _clean(pool):
    async with pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        await conn.execute(
            "UPDATE gmail_sync_state SET history_id = NULL, last_poll_at = NULL, "
            "last_success_at = NULL, last_error = NULL, consecutive_failures = 0, "
            "llm_degraded = FALSE WHERE id = 1"
        )
        await conn.execute("DELETE FROM gmail_credentials")
    yield


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_dsn=TEST_DSN,
        app_password="test-pass",
        secret_key="test-secret-key",
        mail_worker_enabled=False,
        migrations_dir=MIGRATIONS_DIR,
    )


@pytest_asyncio.fixture
async def api(test_settings):
    """Неавторизованный клиент API (без lifespan: миграции уже применены)."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.dishka_container.close()


@pytest_asyncio.fixture
async def authed(api):
    resp = await api.post("/api/auth/login", json={"password": "test-pass"})
    assert resp.status_code == 204, resp.text
    return api
