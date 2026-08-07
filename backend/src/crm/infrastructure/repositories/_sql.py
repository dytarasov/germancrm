"""Помощники для динамических INSERT/UPDATE по whitelist-колонкам."""

from __future__ import annotations

from typing import Any


def insert_clause(
    fields: dict[str, Any], allowed: set[str], *, start: int = 1
) -> tuple[str, str, list[Any]]:
    cols: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Недопустимая колонка для INSERT: {key}")
        cols.append(key)
        values.append(value)
    placeholders = ", ".join(f"${i}" for i in range(start, start + len(cols)))
    return ", ".join(cols), placeholders, values


def like_pattern(term: str) -> str:
    """Паттерн для ILIKE-поиска с экранированием метасимволов LIKE:
    поиск «100%» не должен матчить всё подряд."""
    escaped = (
        term.strip()
        .lower()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def set_clause(
    fields: dict[str, Any], allowed: set[str], *, start: int = 1
) -> tuple[str, list[Any]]:
    parts: list[str] = []
    values: list[Any] = []
    idx = start
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Недопустимая колонка для UPDATE: {key}")
        parts.append(f"{key} = ${idx}")
        values.append(value)
        idx += 1
    return ", ".join(parts), values
