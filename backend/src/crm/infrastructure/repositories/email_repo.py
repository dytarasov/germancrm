from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from crm.domain.enums import EmailProcessingStatus
from crm.domain.models import EmailEventRow, EmailLogEntry, EmailMessage
from crm.infrastructure.mappers.db_mappers import (
    record_to_email_entry,
    record_to_email_event,
)
from crm.infrastructure.repositories._sql import like_pattern, set_clause

_UPDATABLE = {
    "processing_status",
    "attempts",
    "next_attempt_at",
    "error",
    "event_type",
    "confidence",
    "extracted",
    "llm_model",
    "llm_prompt_tokens",
    "llm_completion_tokens",
    "llm_cost_usd",
    "llm_attempts",
    "processed_at",
}


def _norm(fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    if "processing_status" in out and out["processing_status"] is not None:
        out["processing_status"] = str(out["processing_status"])
    if "event_type" in out and out["event_type"] is not None:
        out["event_type"] = str(out["event_type"])
    if "confidence" in out and isinstance(out["confidence"], float):
        out["confidence"] = Decimal(str(round(out["confidence"], 3)))
    return out


class PgEmailRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def insert_ingested(
        self, msg: EmailMessage, status: EmailProcessingStatus
    ) -> int | None:
        return await self._conn.fetchval(
            """
            INSERT INTO email_log
                (gmail_message_id, gmail_thread_id, message_id_hdr, from_addr, from_domain,
                 subject, sent_at, snippet, body_text, processing_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            msg.gmail_message_id,
            msg.gmail_thread_id,
            msg.message_id_hdr,
            msg.from_addr,
            msg.from_domain,
            msg.subject,
            msg.sent_at,
            msg.snippet,
            msg.body_text,
            str(status),
        )

    async def get(self, email_id: int) -> EmailLogEntry | None:
        row = await self._conn.fetchrow("SELECT * FROM email_log WHERE id = $1", email_id)
        return record_to_email_entry(row) if row else None

    async def fetch_queue(self, *, now: datetime, limit: int) -> list[EmailLogEntry]:
        rows = await self._conn.fetch(
            """
            SELECT * FROM email_log
            WHERE processing_status IN ('new', 'pending_llm')
              AND (next_attempt_at IS NULL OR next_attempt_at <= $1)
            ORDER BY sent_at NULLS LAST, id
            LIMIT $2
            """,
            now,
            limit,
        )
        return [record_to_email_entry(r) for r in rows]

    async def update(self, email_id: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        clause, values = set_clause(_norm(fields), _UPDATABLE, start=2)
        await self._conn.execute(
            f"UPDATE email_log SET {clause} WHERE id = $1", email_id, *values
        )

    async def add_event(
        self,
        *,
        email_id: int,
        event_type: str | None,
        order_id: int | None,
        action: str,
        details: dict[str, Any] | None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO email_event (email_id, event_type, order_id, action, details) "
            "VALUES ($1, $2, $3, $4, $5)",
            email_id,
            str(event_type) if event_type else None,
            order_id,
            str(action),
            details,
        )

    async def list_events(self, limit: int) -> list[EmailEventRow]:
        rows = await self._conn.fetch(
            """
            SELECT ev.*, el.subject, el.from_addr, o.store AS order_store, c.name AS client_name
            FROM email_event ev
            JOIN email_log el ON el.id = ev.email_id
            LEFT JOIN orders o ON o.id = ev.order_id
            LEFT JOIN clients c ON c.id = o.client_id
            ORDER BY ev.created_at DESC, ev.id DESC
            LIMIT $1
            """,
            limit,
        )
        return [record_to_email_event(r) for r in rows]

    async def list_by_status(
        self, statuses: list[EmailProcessingStatus], limit: int
    ) -> list[EmailLogEntry]:
        rows = await self._conn.fetch(
            "SELECT * FROM email_log WHERE processing_status = ANY($1::text[]) "
            "ORDER BY ingested_at DESC LIMIT $2",
            [str(s) for s in statuses],
            limit,
        )
        return [record_to_email_entry(r) for r in rows]

    async def list_all(
        self,
        *,
        status: EmailProcessingStatus | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[EmailLogEntry]:
        pattern = like_pattern(search) if search and search.strip() else None
        rows = await self._conn.fetch(
            """
            SELECT * FROM email_log
            WHERE ($1::text IS NULL OR processing_status = $1)
              AND ($2::text IS NULL
                   OR lower(from_addr) LIKE $2
                   OR lower(coalesce(subject, '')) LIKE $2
                   OR lower(from_domain) LIKE $2)
            ORDER BY COALESCE(sent_at, ingested_at) DESC, id DESC
            LIMIT $3
            """,
            str(status) if status else None,
            pattern,
            limit,
        )
        return [record_to_email_entry(r) for r in rows]

    async def events_for_email(self, email_id: int) -> list[EmailEventRow]:
        rows = await self._conn.fetch(
            """
            SELECT ev.*, el.subject, el.from_addr, o.store AS order_store, c.name AS client_name
            FROM email_event ev
            JOIN email_log el ON el.id = ev.email_id
            LEFT JOIN orders o ON o.id = ev.order_id
            LEFT JOIN clients c ON c.id = o.client_id
            WHERE ev.email_id = $1
            ORDER BY ev.created_at, ev.id
            """,
            email_id,
        )
        return [record_to_email_event(r) for r in rows]

    async def status_counts(self) -> dict[str, int]:
        rows = await self._conn.fetch(
            "SELECT processing_status, COUNT(*) AS cnt FROM email_log GROUP BY processing_status"
        )
        return {r["processing_status"]: r["cnt"] for r in rows}

    async def requeue_filtered_domain(self, domain: str) -> int:
        escaped = (
            domain.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        result = await self._conn.fetch(
            """
            UPDATE email_log
            SET processing_status = 'new', attempts = 0, next_attempt_at = NULL, error = NULL
            WHERE processing_status = 'filtered'
              AND (from_domain = $1 OR from_domain LIKE $2)
            RETURNING id
            """,
            domain,
            f"%.{escaped}",
        )
        return len(result)
