from __future__ import annotations

from types import TracebackType
from typing import Protocol


class UnitOfWork(Protocol):
    """Границы транзакции задаёт сервис: `async with uow:` = BEGIN/COMMIT/ROLLBACK.

    Вложенные входы допустимы (реализация делает SAVEPOINT)."""

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
