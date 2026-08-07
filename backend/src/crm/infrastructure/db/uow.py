from __future__ import annotations

from types import TracebackType

import asyncpg


class AsyncpgUnitOfWork:
    """Обёртка над conn.transaction(). Вложенные входы -> SAVEPOINT (asyncpg сам)."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn
        self._stack: list[asyncpg.transaction.Transaction] = []

    async def __aenter__(self) -> AsyncpgUnitOfWork:
        tx = self._conn.transaction()
        await tx.start()
        self._stack.append(tx)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        tx = self._stack.pop()
        if exc_type is not None:
            await tx.rollback()
        else:
            await tx.commit()
