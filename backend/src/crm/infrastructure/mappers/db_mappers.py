"""Мапперы asyncpg.Record -> доменные dataclasses. Единственное место знания о колонках."""

from __future__ import annotations

from decimal import Decimal

import asyncpg

from crm.domain.enums import (
    EmailAction,
    EmailProcessingStatus,
    OrderStatus,
    StatusSource,
    TrackMatchStatus,
    TrackSource,
)
from crm.domain.models import (
    Client,
    EmailEventRow,
    EmailLogEntry,
    Flight,
    GmailCredentials,
    GmailSyncState,
    Order,
    OrderListRow,
    Payment,
    StatusChange,
    Track,
    TrackCandidate,
)


def record_to_client(r: asyncpg.Record) -> Client:
    return Client(
        id=r["id"],
        name=r["name"],
        contacts=r["contacts"],
        telegram_url=r["telegram_url"],
        note=r["note"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def record_to_order(r: asyncpg.Record) -> Order:
    return Order(
        id=r["id"],
        client_id=r["client_id"],
        store=r["store"],
        store_order_number=r["store_order_number"],
        items=r["items"],
        purchase_price_usd=r["purchase_price_usd"],
        commission_usd=r["commission_usd"],
        weight_kg=r["weight_kg"],
        est_weight_kg=r["est_weight_kg"],
        promised_date=r["promised_date"],
        comment=r["comment"],
        status=OrderStatus(r["status"]),
        refunded_amount_usd=r["refunded_amount_usd"],
        refunded_at=r["refunded_at"],
        flight_id=r["flight_id"],
        copied_from=r["copied_from"],
        purchased_on=r["purchased_on"],
        closed_at=r["closed_at"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def record_to_order_row(r: asyncpg.Record) -> OrderListRow:
    return OrderListRow(
        order=record_to_order(r),
        client_name=r["client_name"],
        paid_usd=r["paid_usd"] or Decimal("0"),
        tracks_count=r["tracks_count"] or 0,
    )


def record_to_track(r: asyncpg.Record) -> Track:
    raw_candidates = r["candidates"]
    candidates = (
        [
            TrackCandidate(
                order_id=c["order_id"],
                score=c["score"],
                reasons=list(c.get("reasons") or []),
                order_label=c.get("order_label") or f"Заказ #{c['order_id']}",
            )
            for c in raw_candidates
        ]
        if raw_candidates
        else None
    )
    return Track(
        id=r["id"],
        tracking_number=r["tracking_number"],
        carrier=r["carrier"],
        order_id=r["order_id"],
        source=TrackSource(r["source"]),
        email_log_id=r["email_log_id"],
        match_status=TrackMatchStatus(r["match_status"]),
        candidates=candidates,
        note=r["note"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        resolved_at=r["resolved_at"],
    )


def record_to_payment(r: asyncpg.Record) -> Payment:
    return Payment(
        id=r["id"],
        order_id=r["order_id"],
        paid_on=r["paid_on"],
        amount_usd=r["amount_usd"],
        comment=r["comment"],
        created_at=r["created_at"],
    )


def record_to_flight(r: asyncpg.Record) -> Flight:
    return Flight(
        id=r["id"],
        departed_on=r["departed_on"],
        cost_usd=r["cost_usd"],
        description=r["description"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        orders_count=r["orders_count"] if "orders_count" in r.keys() else 0,
    )


def record_to_status_change(r: asyncpg.Record) -> StatusChange:
    return StatusChange(
        id=r["id"],
        order_id=r["order_id"],
        old_status=OrderStatus(r["old_status"]) if r["old_status"] else None,
        new_status=OrderStatus(r["new_status"]),
        source=StatusSource(r["source"]),
        email_log_id=r["email_log_id"],
        comment=r["comment"],
        changed_at=r["changed_at"],
    )


def record_to_email_entry(r: asyncpg.Record) -> EmailLogEntry:
    return EmailLogEntry(
        id=r["id"],
        gmail_message_id=r["gmail_message_id"],
        from_addr=r["from_addr"],
        from_domain=r["from_domain"],
        subject=r["subject"],
        sent_at=r["sent_at"],
        snippet=r["snippet"],
        body_text=r["body_text"],
        processing_status=EmailProcessingStatus(r["processing_status"]),
        attempts=r["attempts"],
        next_attempt_at=r["next_attempt_at"],
        error=r["error"],
        event_type=r["event_type"],
        confidence=r["confidence"],
        extracted=r["extracted"],
        processed_at=r["processed_at"],
        ingested_at=r["ingested_at"],
    )


def record_to_email_event(r: asyncpg.Record) -> EmailEventRow:
    order_label = None
    if r["order_id"] is not None and "client_name" in r.keys():
        order_label = f"Заказ #{r['order_id']} · {r['client_name']} · {r['order_store']}"
    return EmailEventRow(
        id=r["id"],
        email_id=r["email_id"],
        event_type=r["event_type"],
        order_id=r["order_id"],
        action=EmailAction(r["action"]),
        details=r["details"],
        created_at=r["created_at"],
        subject=r["subject"] if "subject" in r.keys() else None,
        from_addr=r["from_addr"] if "from_addr" in r.keys() else None,
        order_label=order_label,
    )


def record_to_gmail_credentials(r: asyncpg.Record) -> GmailCredentials:
    return GmailCredentials(
        email_address=r["email_address"],
        refresh_token=r["refresh_token"],
        access_token=r["access_token"],
        access_token_expires_at=r["access_token_expires_at"],
        revoked_at=r["revoked_at"],
    )


def record_to_gmail_sync_state(r: asyncpg.Record) -> GmailSyncState:
    history_id = r["history_id"]
    return GmailSyncState(
        history_id=int(history_id) if history_id is not None else None,
        last_poll_at=r["last_poll_at"],
        last_success_at=r["last_success_at"],
        last_error=r["last_error"],
        consecutive_failures=r["consecutive_failures"],
        llm_degraded=r["llm_degraded"],
    )
