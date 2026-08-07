"""Мапперы DM -> DTO (pydantic). Вся сборка ответов API — здесь."""

from __future__ import annotations

from datetime import date

from crm.application.services.client_service import ClientDetail
from crm.application.services.flight_service import FlightDetail
from crm.application.services.matching import MatchCandidate, order_label
from crm.application.services.order_service import OrderDetail
from crm.application.services.settings_service import SettingsView
from crm.domain import rules
from crm.domain.models import (
    Client,
    ClientListItem,
    EmailEventRow,
    EmailLogEntry,
    Flight,
    MailHealth,
    OrderListRow,
    Payment,
    StatusChange,
    Track,
)
from crm.presentation.schemas.clients import ClientDetailOut, ClientListItemOut, ClientOut
from crm.presentation.schemas.dashboard import MailHealthOut
from crm.presentation.schemas.flights import FlightDetailOut, FlightOut
from crm.presentation.schemas.mail import EmailDetailOut, EmailRowOut, MailEventOut
from crm.presentation.schemas.orders import (
    FinanceOut,
    OrderDetailOut,
    OrderItemOut,
    OrderListItemOut,
    StatusChangeOut,
)
from crm.presentation.schemas.payments import PaymentOut
from crm.presentation.schemas.settings import GmailConnectionOut, SettingsOut
from crm.presentation.schemas.tracks import SuggestionOut, TrackCandidateOut, TrackOut


def client_to_out(c: Client) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        contacts=c.contacts,
        telegram_url=c.telegram_url,
        note=c.note,
        created_at=c.created_at,
    )


def client_item_to_out(item: ClientListItem) -> ClientListItemOut:
    return ClientListItemOut(
        id=item.client.id,
        name=item.client.name,
        contacts=item.client.contacts,
        telegram_url=item.client.telegram_url,
        active_orders=item.active_orders,
        debt_usd=item.debt_usd,
    )


def client_detail_to_out(detail: ClientDetail, today: date) -> ClientDetailOut:
    return ClientDetailOut(
        client=client_to_out(detail.client),
        orders=[order_row_to_out(r, today) for r in detail.orders],
        debt_usd=detail.stats.debt_usd,
        earned_usd=detail.stats.earned_usd,
    )


def order_row_to_out(row: OrderListRow, today: date) -> OrderListItemOut:
    o = row.order
    return OrderListItemOut(
        id=o.id,
        client_id=o.client_id,
        client_name=row.client_name,
        store=o.store,
        store_order_number=o.store_order_number,
        items=o.items,
        status=o.status.value,
        purchase_price_usd=o.purchase_price_usd,
        commission_usd=o.commission_usd,
        weight_kg=o.weight_kg,
        promised_date=o.promised_date,
        purchased_on=o.purchased_on,
        is_overdue=rules.is_overdue(o.status, o.promised_date, today),
        paid_usd=row.paid_usd,
        due_usd=rules.due_usd(o.purchase_price_usd, o.commission_usd, row.paid_usd),
        tracks_count=row.tracks_count,
    )


def status_change_to_out(s: StatusChange) -> StatusChangeOut:
    return StatusChangeOut(
        id=s.id,
        old_status=s.old_status.value if s.old_status else None,
        new_status=s.new_status.value,
        source=s.source.value,
        comment=s.comment,
        changed_at=s.changed_at,
    )


def order_detail_to_out(detail: OrderDetail, today: date) -> OrderDetailOut:
    o = detail.order
    finance = detail.finance
    return OrderDetailOut(
        id=o.id,
        client_id=o.client_id,
        client_name=detail.client_name,
        store=o.store,
        store_order_number=o.store_order_number,
        items=o.items,
        status=o.status.value,
        purchase_price_usd=o.purchase_price_usd,
        commission_usd=o.commission_usd,
        weight_kg=o.weight_kg,
        promised_date=o.promised_date,
        purchased_on=o.purchased_on,
        is_overdue=rules.is_overdue(o.status, o.promised_date, today),
        paid_usd=detail.paid_usd,
        due_usd=finance.due_usd,
        tracks_count=detail.tracks_count,
        weight_is_final=o.weight_is_final,
        comment=o.comment,
        refunded_amount_usd=o.refunded_amount_usd,
        refunded_at=o.refunded_at,
        flight_id=o.flight_id,
        copied_from=o.copied_from,
        closed_at=o.closed_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
        tracks=[track_to_out(t) for t in detail.tracks],
        payments=[payment_to_out(p) for p in detail.payments],
        history=[status_change_to_out(s) for s in detail.history],
        order_items=[order_item_to_out(i) for i in detail.order_items],
        finance=FinanceOut(
            revenue_usd=finance.revenue_usd,
            paid_usd=finance.paid_usd,
            due_usd=finance.due_usd,
        ),
    )


def order_item_to_out(i) -> OrderItemOut:
    return OrderItemOut(
        id=i.id,
        order_id=i.order_id,
        title=i.title,
        url=i.url,
        quantity=i.quantity,
        note=i.note,
    )


def track_to_out(t: Track) -> TrackOut:
    return TrackOut(
        id=t.id,
        tracking_number=t.tracking_number,
        carrier=t.carrier,
        order_id=t.order_id,
        source=t.source.value,
        match_status=t.match_status.value,
        candidates=(
            [
                TrackCandidateOut(
                    order_id=c.order_id,
                    score=c.score,
                    reasons=c.reasons,
                    order_label=c.order_label,
                )
                for c in t.candidates
            ]
            if t.candidates
            else None
        ),
        note=t.note,
        created_at=t.created_at,
    )


def suggestion_to_out(c: MatchCandidate) -> SuggestionOut:
    return SuggestionOut(
        order_id=c.row.order.id,
        order_label=order_label(c.row),
        client_name=c.row.client_name,
        score=c.score,
        reasons=c.reasons,
    )


def payment_to_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        order_id=p.order_id,
        paid_on=p.paid_on,
        amount_usd=p.amount_usd,
        comment=p.comment,
    )


def flight_to_out(f: Flight) -> FlightOut:
    return FlightOut(
        id=f.id,
        departed_on=f.departed_on,
        cost_usd=f.cost_usd,
        description=f.description,
        orders_count=f.orders_count,
    )


def flight_detail_to_out(detail: FlightDetail, today: date) -> FlightDetailOut:
    base = flight_to_out(detail.flight)
    return FlightDetailOut(
        **base.model_dump(),
        orders=[order_row_to_out(r, today) for r in detail.orders],
    )


def mail_health_to_out(h: MailHealth) -> MailHealthOut:
    return MailHealthOut(
        configured=h.configured,
        gmail_connected=h.gmail_connected,
        gmail_email=h.gmail_email,
        needs_reauth=h.needs_reauth,
        last_success_at=h.last_success_at,
        llm_degraded=h.llm_degraded,
        pending_llm=h.pending_llm,
        manual_review=h.manual_review,
        poison=h.poison,
        open_tracks=h.open_tracks,
        worker_ok=h.worker_ok,
    )


def email_row_to_out(e: EmailLogEntry) -> EmailRowOut:
    return EmailRowOut(
        id=e.id,
        from_addr=e.from_addr,
        subject=e.subject,
        sent_at=e.sent_at,
        processing_status=e.processing_status.value,
        error=e.error,
        snippet=e.snippet,
        event_type=e.event_type,
        confidence=float(e.confidence) if e.confidence is not None else None,
    )


def email_detail_to_out(e: EmailLogEntry) -> EmailDetailOut:
    base = email_row_to_out(e)
    return EmailDetailOut(
        **base.model_dump(),
        from_domain=e.from_domain,
        body_text=e.body_text,
        extracted=e.extracted,
    )


def mail_event_to_out(e: EmailEventRow) -> MailEventOut:
    details = e.details or {}
    return MailEventOut(
        id=e.id,
        created_at=e.created_at,
        action=e.action.value,
        event_type=e.event_type,
        summary=details.get("summary"),
        order_id=e.order_id,
        order_label=e.order_label,
        subject=e.subject,
        from_addr=e.from_addr,
    )


def settings_view_to_out(view: SettingsView) -> SettingsOut:
    v = view.values
    return SettingsOut(
        llm_model=v.get("llm_model") or "",
        llm_enabled=bool(v.get("llm_enabled", True)),
        llm_auto_min_confidence=float(v.get("llm_auto_min_confidence") or 0.75),
        poll_interval_sec=int(v.get("poll_interval_sec") or 180),
        backfill_days=int(v.get("backfill_days") or 30),
        whitelist_domains=list(v.get("whitelist_domains") or []),
        forwarder_domains=list(v.get("forwarder_domains") or []),
        gmail_query=str(v.get("gmail_query") or ""),
        auto_threshold=int(v.get("auto_threshold") or 80),
        suggest_threshold=int(v.get("suggest_threshold") or 40),
        gmail=GmailConnectionOut(
            connected=view.gmail.connected,
            email=view.gmail.email,
            needs_reauth=view.gmail.needs_reauth,
        ),
    )
