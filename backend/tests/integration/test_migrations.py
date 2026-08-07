from __future__ import annotations

from pathlib import Path

import pytest

from crm.infrastructure.db.migrations import MigrationError, MigrationRunner
from tests.integration.conftest import MIGRATIONS_DIR


async def test_rerun_is_noop(pool):
    applied = await MigrationRunner(pool, MIGRATIONS_DIR).run()
    assert applied == []


async def test_tampered_migration_fails_fast(pool, tmp_path: Path):
    extra = tmp_path / "9999_test_probe.sql"
    extra.write_text("SELECT 1;", encoding="utf-8")
    runner = MigrationRunner(pool, tmp_path)

    applied = await runner.run()
    assert applied == [9999]
    assert await MigrationRunner(pool, tmp_path).run() == []

    extra.write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(MigrationError, match="checksum"):
        await MigrationRunner(pool, tmp_path).run()

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM schema_migrations WHERE version = 9999")


async def test_failed_migration_rolls_back(pool, tmp_path: Path):
    bad = tmp_path / "9998_bad_probe.sql"
    bad.write_text(
        "CREATE TABLE probe_should_not_exist (id INT); SELECT broken syntax;",
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        await MigrationRunner(pool, tmp_path).run()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT to_regclass('probe_should_not_exist')")
        recorded = await conn.fetchval(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 9998"
        )
    assert exists is None
    assert recorded == 0
