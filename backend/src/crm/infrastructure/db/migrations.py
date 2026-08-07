"""Кастомный migration runner: plain .sql файлы `NNNN_name.sql`, применяется в lifespan.

- pg_advisory_lock: при нескольких процессах мигрирует ровно один, остальные ждут.
- sha256-checksum применённых файлов сверяется: правка задним числом = ошибка старта.
- Каждая миграция в своей транзакции вместе с записью в schema_migrations.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import asyncpg

log = logging.getLogger("crm.migrations")

MIGRATION_LOCK_KEY = 0x6765726D_637201  # 'germcr' + 01
_FILE_RE = re.compile(r"^(\d{4})_[\w\-]+\.sql$")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: int
    name: str
    path: Path
    sql: str
    checksum: str


def load_migration_files(migrations_dir: Path) -> list[MigrationFile]:
    if not migrations_dir.is_dir():
        raise MigrationError(f"Каталог миграций не найден: {migrations_dir}")
    files: list[MigrationFile] = []
    for path in sorted(migrations_dir.iterdir()):
        m = _FILE_RE.match(path.name)
        if not m:
            continue
        sql = path.read_text(encoding="utf-8")
        files.append(
            MigrationFile(
                version=int(m.group(1)),
                name=path.stem,
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    versions = [f.version for f in files]
    if len(versions) != len(set(versions)):
        raise MigrationError("Дублирующиеся версии миграций")
    return files


class MigrationRunner:
    def __init__(self, pool: asyncpg.Pool, migrations_dir: Path) -> None:
        self._pool = pool
        self._dir = migrations_dir

    async def run(self) -> list[int]:
        files = load_migration_files(self._dir)
        applied_now: list[int] = []
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_KEY)
            try:
                await conn.execute(_CREATE_TABLE)
                rows = await conn.fetch("SELECT version, checksum FROM schema_migrations")
                applied = {r["version"]: r["checksum"] for r in rows}
                for f in files:
                    if f.version in applied:
                        if applied[f.version] != f.checksum:
                            raise MigrationError(
                                f"Миграция {f.name} изменена после применения "
                                f"(checksum не совпадает). Откатите правку или создайте новую миграцию."
                            )
                        continue
                    log.info("Применяю миграцию %s", f.name)
                    async with conn.transaction():
                        await conn.execute(f.sql)
                        await conn.execute(
                            "INSERT INTO schema_migrations (version, name, checksum) "
                            "VALUES ($1, $2, $3)",
                            f.version,
                            f.name,
                            f.checksum,
                        )
                    applied_now.append(f.version)
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)
        if applied_now:
            log.info("Применены миграции: %s", applied_now)
        return applied_now
