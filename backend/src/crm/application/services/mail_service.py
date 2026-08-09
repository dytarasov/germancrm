"""Почтовый конвейер: две фазы с состоянием в БД.

Фаза A (ingest): Gmail -> email_log(new|filtered) -> курсор historyId.
Фаза B (process): очередь email_log -> LLM -> валидация -> матчинг -> статусы/треки/события.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crm.application.interfaces.gdrive import DrivePort, DriveScopeError
from crm.application.interfaces.gmail import (
    GmailAuthError,
    GmailHistoryExpiredError,
    GmailPort,
)
from crm.application.interfaces.llm import (
    LLMExtractor,
    LLMUnavailableError,
    LLMValidationError,
)
from crm.application.interfaces.repositories import (
    EmailRepository,
    GmailStateRepository,
    OrderRepository,
    SettingsRepository,
    TrackRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.application.services.carriers import infer_carrier, is_plausible_tracking_number
from crm.application.services.matching import MatcherService, normalize_number, order_label
from crm.application.services.order_service import OrderService
from crm.application.services.settings_service import DEFAULTS
from crm.application.services.track_service import normalize_tracking_number
from crm.domain.clock import business_today
from crm.domain.enums import (
    EmailAction,
    EmailEventType,
    EmailProcessingStatus,
    OrderStatus,
    StatusSource,
    TrackMatchStatus,
    TrackSource,
)
from crm.domain.exceptions import ConflictError, DomainValidationError, NotFoundError
from crm.domain.models import (
    EmailExtraction,
    EmailLogEntry,
    ExtractedTrack,
    MailHealth,
    Track,
)

log = logging.getLogger("crm.mail")

MAX_EMAILS_PER_CYCLE = 50
MAX_INGEST_PER_CYCLE = 200
DRIVE_BACKUP_FOLDER = "shaprivezu-backups"
DRIVE_BACKUP_KEEP = 60
MAX_BACKFILL_MESSAGES = 1000
POISON_AFTER_ATTEMPTS = 5
RETRY_BACKOFF = [timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=8)]
LLM_UNAVAILABLE_CIRCUIT = 3


def domain_in_list(domain: str, allowed: list[str]) -> bool:
    domain = domain.lower()
    return any(domain == d or domain.endswith("." + d) for d in allowed if d)


def guard_extraction(extraction: EmailExtraction, body_text: str | None) -> EmailExtraction:
    """Анти-галлюцинация: извлечённые номера обязаны буквально присутствовать в письме."""
    haystack = normalize_number(body_text or "")
    tracks = [t for t in extraction.tracking_numbers if normalize_number(t.number) in haystack]
    order_number = extraction.order_number
    if order_number and normalize_number(order_number) not in haystack:
        order_number = None
    if len(tracks) == len(extraction.tracking_numbers) and order_number == extraction.order_number:
        return extraction
    return EmailExtraction(
        event_type=extraction.event_type,
        confidence=extraction.confidence,
        store_domain=extraction.store_domain,
        order_number=order_number,
        tracking_numbers=tracks,
        carrier=extraction.carrier,
        summary=extraction.summary,
        reasoning=extraction.reasoning,
    )


def enrich_extraction(extraction: EmailExtraction) -> EmailExtraction:
    """Детерминированная чистка после LLM: нормализация треков, определение
    перевозчика по формату номера, отбрасывание неправдоподобных «номеров».
    Классификация остаётся за LLM — здесь только качество данных."""
    tracks: list[ExtractedTrack] = []
    for t in extraction.tracking_numbers:
        number = normalize_number(t.number)
        if not is_plausible_tracking_number(number):
            log.info("Отброшен неправдоподобный трек от LLM: %r", t.number)
            continue
        carrier = (
            (t.carrier or "").strip().lower()
            or infer_carrier(number)
            or (extraction.carrier or "").strip().lower()
            or None
        )
        tracks.append(ExtractedTrack(number=number, carrier=carrier))
    if tracks == extraction.tracking_numbers:
        return extraction
    return EmailExtraction(
        event_type=extraction.event_type,
        confidence=extraction.confidence,
        store_domain=extraction.store_domain,
        order_number=extraction.order_number,
        tracking_numbers=tracks,
        carrier=extraction.carrier,
        summary=extraction.summary,
        reasoning=extraction.reasoning,
    )


@dataclass(frozen=True, slots=True)
class ReviewLists:
    emails: list[EmailLogEntry]
    filtered: list[EmailLogEntry]
    open_tracks: list[Track]


@dataclass(frozen=True, slots=True)
class ProcessStats:
    processed: int = 0
    manual: int = 0
    pending_llm: int = 0
    failed: int = 0


class MailService:
    def __init__(
        self,
        gmail: GmailPort,
        gmail_state: GmailStateRepository,
        emails: EmailRepository,
        settings: SettingsRepository,
        orders: OrderRepository,
        tracks: TrackRepository,
        order_service: OrderService,
        matcher: MatcherService,
        llm: LLMExtractor,
        uow: UnitOfWork,
        *,
        gmail_configured: bool,
        drive: DrivePort | None = None,
        backups_dir: Path | None = None,
    ) -> None:
        self._gmail = gmail
        self._gmail_state = gmail_state
        self._emails = emails
        self._settings = settings
        self._orders = orders
        self._tracks = tracks
        self._order_service = order_service
        self._matcher = matcher
        self._llm = llm
        self._uow = uow
        self._gmail_configured = gmail_configured
        self._drive = drive
        self._backups_dir = backups_dir

    # ---------------- OAuth ----------------

    async def oauth_url(self, state: str) -> str:
        if not self._gmail_configured:
            raise ConflictError(
                "Gmail не настроен: задайте GOOGLE_OAUTH_CLIENT_ID/SECRET в .env"
            )
        return self._gmail.build_auth_url(state)

    async def oauth_complete(self, code: str) -> str:
        tokens = await self._gmail.exchange_code(code)
        if not tokens.refresh_token:
            raise DomainValidationError(
                "Google не вернул refresh token. Удалите доступ приложения в настройках "
                "Google-аккаунта и подключите Gmail заново"
            )
        profile = await self._gmail.get_profile(tokens.access_token)
        async with self._uow:
            await self._gmail_state.save_credentials(
                email_address=profile.email,
                refresh_token=tokens.refresh_token,
                access_token=tokens.access_token,
                expires_at=_now() + timedelta(seconds=max(tokens.expires_in - 60, 60)),
            )
            # Сбрасываем курсор: первичная синхронизация начнётся со следующего цикла.
            await self._gmail_state.update_sync_state(
                {"history_id": None, "last_error": None, "consecutive_failures": 0}
            )
        log.info("Gmail подключён: %s", profile.email)
        return profile.email

    # ---------------- Фаза A: ingest ----------------

    async def ingest_cycle(self) -> int:
        creds = await self._gmail_state.get_credentials()
        if creds is None or creds.revoked_at is not None:
            return 0
        token = await self._access_token()
        state = await self._gmail_state.get_sync_state()
        whitelist = await self._allowed_domains()

        inserted = 0
        if state.history_id is None:
            latest_history_id, inserted = await self._initial_sync(token, whitelist)
        else:
            try:
                latest_history_id, inserted = await self._incremental_sync(
                    token, state.history_id, whitelist
                )
            except GmailHistoryExpiredError:
                log.warning("historyId протух — полный ресинк")
                latest_history_id, inserted = await self._resync(
                    token, state.last_success_at, whitelist
                )

        fields: dict = {
            "last_poll_at": _now(),
            "last_success_at": _now(),
            "consecutive_failures": 0,
            "last_error": None,
        }
        if latest_history_id is not None:
            fields["history_id"] = latest_history_id
        await self._gmail_state.update_sync_state(fields)
        return inserted

    async def _initial_sync(self, token: str, whitelist: list[str]) -> tuple[int | None, int]:
        profile = await self._gmail.get_profile(token)
        backfill_days = int(await self._setting("mail.backfill_days"))
        query = f"newer_than:{backfill_days}d {await self._setting('mail.gmail_query') or ''}".strip()
        inserted = await self._ingest_by_query(token, query, whitelist)
        return profile.history_id, inserted

    async def _incremental_sync(
        self, token: str, cursor: int, whitelist: list[str]
    ) -> tuple[int | None, int]:
        """Курсор двигается по id ОБРАБОТАННЫХ записей истории.

        historyId из корня ответа history.list — это текущий id всего ящика,
        а не «докуда дочитали»: прыгнуть на него можно только дочитав все
        страницы. При бэклоге больше лимита останавливаемся на последней
        обработанной записи — хвост доберут следующие циклы, письма не теряются."""
        fetched = 0
        inserted = 0
        last_record_id: int | None = None
        mailbox_history_id: int | None = None
        page_token: str | None = None
        while True:
            page = await self._gmail.list_history(token, cursor, page_token)
            mailbox_history_id = page.mailbox_history_id or mailbox_history_id
            for record in page.records:
                if fetched >= MAX_INGEST_PER_CYCLE:
                    log.info(
                        "Бэклог почты больше %s писем — продолжу со следующего цикла",
                        MAX_INGEST_PER_CYCLE,
                    )
                    return last_record_id, inserted
                inserted += await self._ingest_messages(token, record.message_ids, whitelist)
                fetched += len(record.message_ids)
                last_record_id = record.id
            page_token = page.next_page_token
            if not page_token:
                break
        # история дочитана целиком — безопасно прыгнуть на текущий historyId ящика
        return mailbox_history_id or last_record_id, inserted

    async def _resync(
        self, token: str, last_success_at: datetime | None, whitelist: list[str]
    ) -> tuple[int | None, int]:
        # historyId фиксируем ДО листинга: письма, пришедшие во время ресинка,
        # попадут в следующий инкрементальный проход, а не потеряются.
        profile = await self._gmail.get_profile(token)
        backfill_days = int(await self._setting("mail.backfill_days"))
        cap = max(backfill_days, 7)
        days = 7
        if last_success_at is not None:
            gap = (_now() - last_success_at).days + 2
            days = min(max(gap, 2), cap)
            if gap > cap:
                log.warning(
                    "Ресинк покрывает %s дн., а простой был %s дн. — письма старше окна "
                    "не будут прочитаны автоматически",
                    days,
                    gap,
                )
        query = f"newer_than:{days}d {await self._setting('mail.gmail_query') or ''}".strip()
        inserted = await self._ingest_by_query(token, query, whitelist)
        return profile.history_id, inserted

    async def _ingest_by_query(self, token: str, query: str, whitelist: list[str]) -> int:
        message_ids: list[str] = []
        page_token: str | None = None
        while True:
            page = await self._gmail.list_messages(token, query=query, page_token=page_token)
            message_ids.extend(page.message_ids)
            page_token = page.next_page_token
            if not page_token or len(message_ids) >= MAX_BACKFILL_MESSAGES:
                break
        if len(message_ids) > MAX_BACKFILL_MESSAGES:
            log.warning(
                "Бэкфилл обрезан до %s писем (query=%r) — старые письма пропущены",
                MAX_BACKFILL_MESSAGES,
                query,
            )
            message_ids = message_ids[:MAX_BACKFILL_MESSAGES]
        return await self._ingest_messages(token, message_ids, whitelist)

    async def _ingest_messages(
        self, token: str, message_ids: list[str], whitelist: list[str]
    ) -> int:
        inserted = 0
        for message_id in message_ids:
            msg = await self._gmail.get_message(token, message_id)
            if msg is None:
                # письмо удалили до скачивания — пропускаем
                continue
            status = (
                EmailProcessingStatus.NEW
                if domain_in_list(msg.from_domain, whitelist)
                else EmailProcessingStatus.FILTERED
            )
            if await self._emails.insert_ingested(msg, status) is not None:
                inserted += 1
        return inserted

    async def _access_token(self) -> str:
        creds = await self._gmail_state.get_credentials()
        assert creds is not None
        if (
            creds.access_token
            and creds.access_token_expires_at
            and creds.access_token_expires_at > _now() + timedelta(minutes=5)
        ):
            return creds.access_token
        try:
            tokens = await self._gmail.refresh_access_token(creds.refresh_token)
        except GmailAuthError:
            await self._gmail_state.mark_revoked()
            raise
        expires_at = _now() + timedelta(seconds=max(tokens.expires_in - 60, 60))
        await self._gmail_state.update_access_token(tokens.access_token, expires_at)
        return tokens.access_token

    # ---------------- Фаза B: process ----------------

    async def process_cycle(self, now: datetime | None = None) -> ProcessStats:
        now = now or _now()
        rows = await self._emails.fetch_queue(now=now, limit=MAX_EMAILS_PER_CYCLE)
        processed = manual = pending = failed = 0
        llm_unavailable_streak = 0

        for row in rows:
            if llm_unavailable_streak >= LLM_UNAVAILABLE_CIRCUIT:
                break
            try:
                extraction, usage = await self._llm.extract(
                    from_addr=row.from_addr,
                    subject=row.subject,
                    sent_at=row.sent_at,
                    body_text=row.body_text or "",
                )
            except LLMUnavailableError as exc:
                pending += 1
                llm_unavailable_streak += 1
                await self._emails.update(
                    row.id,
                    {"processing_status": EmailProcessingStatus.PENDING_LLM, "error": str(exc)},
                )
                continue
            except LLMValidationError as exc:
                manual += 1
                await self._emails.update(
                    row.id,
                    {"processing_status": EmailProcessingStatus.MANUAL_REVIEW, "error": str(exc)},
                )
                await self._emails.add_event(
                    email_id=row.id,
                    event_type=None,
                    order_id=None,
                    action=EmailAction.MANUAL_REVIEW,
                    details={"reason": "llm_validation_failed"},
                )
                continue
            except Exception as exc:  # noqa: BLE001 — сбой на одном письме не стопорит очередь
                failed += 1
                log.exception("Неожиданная ошибка LLM-вызова на письме id=%s", row.id)
                await self._register_failure(row, exc, now)
                continue

            llm_unavailable_streak = 0
            # Subject тоже часть письма: номера заказов часто лежат только в теме.
            extraction = enrich_extraction(
                guard_extraction(extraction, f"{row.subject or ''}\n{row.body_text or ''}")
            )
            # Расход LLM пишем ВНЕ транзакции применения: токены потрачены,
            # даже если применение упадёт и письмо уйдёт в ретрай.
            await self._emails.update(
                row.id,
                {
                    "event_type": extraction.event_type,
                    "confidence": extraction.confidence,
                    "extracted": asdict(extraction),
                    "llm_model": usage.model,
                    "llm_prompt_tokens": usage.prompt_tokens,
                    "llm_completion_tokens": usage.completion_tokens,
                    "llm_cost_usd": usage.cost_usd,
                    "llm_attempts": usage.attempts,
                },
            )
            try:
                async with self._uow:
                    # Пока ждали LLM, письмо могли разобрать вручную (resolve) —
                    # не применяем второй раз. FOR UPDATE: если ручной разбор идёт
                    # прямо сейчас, ждём его коммита и увидим уже финальный статус.
                    fresh = await self._emails.get(row.id, for_update=True)
                    if fresh is None or fresh.processing_status not in (
                        EmailProcessingStatus.NEW,
                        EmailProcessingStatus.PENDING_LLM,
                    ):
                        continue
                    final_status = await self._apply(row, extraction)
                    await self._emails.update(
                        row.id,
                        {
                            "processing_status": final_status,
                            "processed_at": _now(),
                            "error": None,
                            "next_attempt_at": None,
                        },
                    )
                if final_status == EmailProcessingStatus.MANUAL_REVIEW:
                    manual += 1
                else:
                    processed += 1
            except Exception as exc:  # noqa: BLE001 — poison-обработка, письмо не должно ронять цикл
                failed += 1
                log.exception("Ошибка обработки письма id=%s", row.id)
                await self._register_failure(row, exc, now)

        degraded = llm_unavailable_streak >= LLM_UNAVAILABLE_CIRCUIT
        # (poison/backoff одного письма никогда не останавливает хвост очереди)
        state = await self._gmail_state.get_sync_state()
        if state.llm_degraded != degraded:
            await self._gmail_state.update_sync_state({"llm_degraded": degraded})
        return ProcessStats(processed=processed, manual=manual, pending_llm=pending, failed=failed)

    async def _register_failure(self, row: EmailLogEntry, exc: Exception, now: datetime) -> None:
        attempts = row.attempts + 1
        if attempts >= POISON_AFTER_ATTEMPTS:
            fields: dict = {
                "processing_status": EmailProcessingStatus.POISON,
                "attempts": attempts,
                "error": str(exc),
            }
        else:
            backoff = RETRY_BACKOFF[min(attempts - 1, len(RETRY_BACKOFF) - 1)]
            fields = {"attempts": attempts, "next_attempt_at": now + backoff, "error": str(exc)}
        await self._emails.update(row.id, fields)

    async def _apply(self, row: EmailLogEntry, e: EmailExtraction) -> EmailProcessingStatus:
        event = e.event_type
        if event == EmailEventType.OTHER:
            return EmailProcessingStatus.IGNORED

        if event == EmailEventType.DELIVERY_UPDATE:
            await self._emails.add_event(
                email_id=row.id,
                event_type=event,
                order_id=None,
                action=EmailAction.INFO,
                details={"summary": e.summary},
            )
            return EmailProcessingStatus.PROCESSED

        if event == EmailEventType.CANCELLATION_OR_REFUND:
            await self._emails.add_event(
                email_id=row.id,
                event_type=event,
                order_id=None,
                action=EmailAction.MANUAL_REVIEW,
                details={"summary": e.summary},
            )
            return EmailProcessingStatus.MANUAL_REVIEW

        candidates = await self._orders.candidates_for_matching(
            statuses=[OrderStatus.PURCHASED, OrderStatus.SHIPPED], max_age_days=60
        )
        auto_threshold = int(await self._setting("matching.auto_threshold"))
        min_confidence = float(await self._setting("llm.auto_min_confidence"))
        confident_allowed = e.confidence >= min_confidence

        if event == EmailEventType.ORDER_CONFIRMATION:
            scored = self._matcher.score_orders(
                candidates, store_domain=e.store_domain, order_number=e.order_number
            )
            if (
                e.order_number
                and confident_allowed
                and self._matcher.is_confident(scored, auto_threshold=auto_threshold)
                and scored[0].row.order.store_order_number is None
            ):
                target = scored[0].row
                await self._orders.update_fields(
                    target.order.id, {"store_order_number": e.order_number}
                )
                await self._emails.add_event(
                    email_id=row.id,
                    event_type=event,
                    order_id=target.order.id,
                    action=EmailAction.ORDER_NO_LINKED,
                    details={"summary": e.summary, "order_number": e.order_number},
                )
            else:
                await self._emails.add_event(
                    email_id=row.id,
                    event_type=event,
                    order_id=None,
                    action=EmailAction.INFO,
                    details={"summary": e.summary, "order_number": e.order_number},
                )
            return EmailProcessingStatus.PROCESSED

        if event == EmailEventType.SHIPPED:
            if not e.tracking_numbers:
                await self._emails.add_event(
                    email_id=row.id,
                    event_type=event,
                    order_id=None,
                    action=EmailAction.MANUAL_REVIEW,
                    details={"summary": e.summary, "reason": "shipped_without_track"},
                )
                return EmailProcessingStatus.MANUAL_REVIEW
            for tn in e.tracking_numbers:
                await self._handle_shipped_track(
                    row, e, tn.number, tn.carrier or e.carrier, candidates,
                    auto_threshold=auto_threshold, confident_allowed=confident_allowed,
                )
            return EmailProcessingStatus.PROCESSED

        if event == EmailEventType.ARRIVED_AT_WAREHOUSE:
            return await self._handle_arrived(row, e, candidates, auto_threshold, confident_allowed)

        return EmailProcessingStatus.MANUAL_REVIEW

    async def _handle_shipped_track(
        self,
        row: EmailLogEntry,
        e: EmailExtraction,
        raw_number: str,
        carrier: str | None,
        candidates: list,
        *,
        auto_threshold: int,
        confident_allowed: bool,
    ) -> None:
        number = normalize_tracking_number(raw_number)
        existing = await self._tracks.get_by_number(number)
        if existing is not None and existing.match_status == TrackMatchStatus.DISMISSED:
            # человек уже пометил трек как «не относится» — автоматика решение не отменяет
            await self._emails.add_event(
                email_id=row.id,
                event_type=e.event_type,
                order_id=None,
                action=EmailAction.INFO,
                details={
                    "tracking_number": number,
                    "reason": "track_dismissed_by_user",
                    "summary": e.summary,
                },
            )
            return
        scored = self._matcher.score_orders(
            candidates,
            store_domain=e.store_domain,
            order_number=e.order_number,
            target_status=OrderStatus.SHIPPED,
        )

        if existing is not None and existing.order_id is not None:
            # Повторное письмо про известный трек: двигаем статус, но только
            # если событию можно доверять — confidence относится к event_type.
            if confident_allowed:
                await self._advance(row, e, existing.order_id, OrderStatus.SHIPPED)
            else:
                await self._emails.add_event(
                    email_id=row.id,
                    event_type=e.event_type,
                    order_id=existing.order_id,
                    action=EmailAction.INFO,
                    details={"summary": e.summary, "reason": "low_confidence"},
                )
            return

        if confident_allowed and self._matcher.is_confident(scored, auto_threshold=auto_threshold):
            target = scored[0].row
            if existing is not None:
                await self._tracks.update(
                    existing.id,
                    {
                        "order_id": target.order.id,
                        "match_status": TrackMatchStatus.LINKED,
                        "resolved_at": _now(),
                        "candidates": None,
                    },
                )
            else:
                await self._tracks.add(
                    tracking_number=number,
                    carrier=carrier,
                    order_id=target.order.id,
                    source=TrackSource.EMAIL,
                    email_log_id=row.id,
                    match_status=TrackMatchStatus.LINKED,
                    candidates=None,
                    note=None,
                )
            await self._emails.add_event(
                email_id=row.id,
                event_type=e.event_type,
                order_id=target.order.id,
                action=EmailAction.TRACK_ADDED,
                details={"tracking_number": number, "summary": e.summary},
            )
            await self._advance(row, e, target.order.id, OrderStatus.SHIPPED)
        else:
            top = [
                {
                    "order_id": c.row.order.id,
                    "score": c.score,
                    "reasons": c.reasons,
                    "order_label": order_label(c.row),
                }
                for c in scored[:3]
            ]
            if existing is None:
                await self._tracks.add(
                    tracking_number=number,
                    carrier=carrier,
                    order_id=None,
                    source=TrackSource.EMAIL,
                    email_log_id=row.id,
                    match_status=TrackMatchStatus.OPEN,
                    candidates=top or None,
                    note=None,
                )
            else:
                await self._tracks.update(existing.id, {"candidates": top or None})
            await self._emails.add_event(
                email_id=row.id,
                event_type=e.event_type,
                order_id=None,
                action=EmailAction.TRACK_SUGGESTED,
                details={"tracking_number": number, "candidates": top, "summary": e.summary},
            )

    async def _handle_arrived(
        self,
        row: EmailLogEntry,
        e: EmailExtraction,
        candidates: list,
        auto_threshold: int,
        confident_allowed: bool,
    ) -> EmailProcessingStatus:
        # Основной путь: письмо склада содержит известный трек.
        for tn in e.tracking_numbers:
            track = await self._tracks.get_by_number(normalize_tracking_number(tn.number))
            if track is not None and track.order_id is not None:
                if not confident_allowed:
                    break  # заказ знаем, но событию не доверяем — в ручной разбор
                await self._advance(row, e, track.order_id, OrderStatus.AT_WAREHOUSE)
                return EmailProcessingStatus.PROCESSED
        # Запасной: скоринг.
        scored = self._matcher.score_orders(
            candidates,
            store_domain=e.store_domain,
            order_number=e.order_number,
            target_status=OrderStatus.AT_WAREHOUSE,
        )
        if confident_allowed and self._matcher.is_confident(scored, auto_threshold=auto_threshold):
            await self._advance(row, e, scored[0].row.order.id, OrderStatus.AT_WAREHOUSE)
            return EmailProcessingStatus.PROCESSED
        await self._emails.add_event(
            email_id=row.id,
            event_type=e.event_type,
            order_id=None,
            action=EmailAction.MANUAL_REVIEW,
            details={"summary": e.summary, "reason": "warehouse_no_match"},
        )
        return EmailProcessingStatus.MANUAL_REVIEW

    async def _advance(
        self, row: EmailLogEntry, e: EmailExtraction, order_id: int, new_status: OrderStatus
    ) -> None:
        outcome = await self._order_service.advance_status_auto(
            order_id, new_status, email_log_id=row.id
        )
        action = {
            "advanced": EmailAction.STATUS_ADVANCED,
            "stale": EmailAction.IGNORED_STALE,
            "terminal": EmailAction.IGNORED_TERMINAL,
        }.get(outcome, EmailAction.INFO)
        await self._emails.add_event(
            email_id=row.id,
            event_type=e.event_type,
            order_id=order_id,
            action=action,
            details={"summary": e.summary, "new_status": new_status, "outcome": outcome},
        )

    # ---------------- Ретро-матчинг ----------------

    async def retro_match(self) -> int:
        """Пересчитывает подсказки-кандидаты у ВСЕХ открытых треков.

        Автопривязку здесь НЕ делаем: один и тот же топ-кандидат привязал бы
        к себе все открытые треки разом — привязка задним числом только руками.
        Но подсказки освежаются каждый цикл: заказ, созданный ПОСЛЕ письма,
        обязан появиться в кандидатах старого трека. Контекст исходного письма
        (магазин, номер заказа) при пересчёте сохраняется через email_log_id."""
        open_tracks = await self._tracks.open_tracks()
        if not open_tracks:
            return 0
        pool = await self._orders.candidates_for_matching(
            statuses=[OrderStatus.PURCHASED, OrderStatus.SHIPPED], max_age_days=60
        )
        refreshed = 0
        for track in open_tracks:
            store_domain = order_number = None
            if track.email_log_id is not None:
                entry = await self._emails.get(track.email_log_id)
                extracted = (entry.extracted or {}) if entry else {}
                store_domain = extracted.get("store_domain")
                order_number = extracted.get("order_number")
            scored = self._matcher.score_orders(
                pool, store_domain=store_domain, order_number=order_number
            )
            top = [
                {
                    "order_id": c.row.order.id,
                    "score": c.score,
                    "reasons": c.reasons,
                    "order_label": order_label(c.row),
                }
                for c in scored[:3]
            ]
            await self._tracks.update(track.id, {"candidates": top or None})
            refreshed += 1
        return refreshed

    # ---------------- Здоровье / UI ----------------

    async def health(self, now: datetime | None = None) -> MailHealth:
        now = now or _now()
        creds = await self._gmail_state.get_credentials()
        state = await self._gmail_state.get_sync_state()
        counts = await self._emails.status_counts()
        open_tracks = await self._tracks.open_tracks()
        interval = int(await self._setting("mail.poll_interval_sec"))
        connected = creds is not None and creds.revoked_at is None
        worker_ok = True
        if connected:
            worker_ok = (
                state.last_success_at is not None
                and (now - state.last_success_at).total_seconds() < 3 * max(interval, 60)
            )
        return MailHealth(
            configured=self._gmail_configured,
            gmail_connected=connected,
            gmail_email=creds.email_address if creds else None,
            needs_reauth=creds is not None and creds.revoked_at is not None,
            last_success_at=state.last_success_at,
            llm_degraded=state.llm_degraded,
            pending_llm=counts.get(EmailProcessingStatus.PENDING_LLM, 0),
            manual_review=counts.get(EmailProcessingStatus.MANUAL_REVIEW, 0),
            poison=counts.get(EmailProcessingStatus.POISON, 0),
            open_tracks=len(open_tracks),
            worker_ok=worker_ok,
        )

    async def events(self, limit: int = 50) -> list:
        return await self._emails.list_events(limit)

    async def review(self) -> ReviewLists:
        return ReviewLists(
            emails=await self._emails.list_by_status(
                [
                    EmailProcessingStatus.MANUAL_REVIEW,
                    EmailProcessingStatus.POISON,
                    EmailProcessingStatus.PENDING_LLM,
                ],
                limit=100,
            ),
            filtered=await self._emails.list_by_status([EmailProcessingStatus.FILTERED], limit=50),
            open_tracks=await self._tracks.open_tracks(),
        )

    async def get_email(self, email_id: int) -> EmailLogEntry:
        email = await self._emails.get(email_id)
        if email is None:
            raise NotFoundError.entity("Письмо", email_id)
        return email

    async def list_emails(
        self,
        *,
        status: EmailProcessingStatus | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[EmailLogEntry]:
        return await self._emails.list_all(status=status, search=search, limit=limit)

    async def email_events(self, email_id: int) -> list:
        await self.get_email(email_id)
        return await self._emails.events_for_email(email_id)

    async def resolve_email(
        self,
        email_id: int,
        *,
        order_id: int,
        event_type: EmailEventType | None = None,
        tracking_numbers: list[str] | None = None,
        carrier: str | None = None,
    ) -> None:
        """Ручной разбор письма из очереди: привязать к заказу, создать/привязать
        треки, при необходимости применить событие. Правила безопасности статусов
        те же, что у автоматики (только вперёд), но в истории source='manual'."""
        email = await self.get_email(email_id)
        if email.processing_status == EmailProcessingStatus.PROCESSED:
            raise ConflictError("Письмо уже разобрано — повторный разбор задублирует события")
        if await self._orders.get(order_id) is None:
            raise NotFoundError.entity("Заказ", order_id)
        if event_type is not None and event_type not in (
            EmailEventType.SHIPPED,
            EmailEventType.ARRIVED_AT_WAREHOUSE,
        ):
            raise DomainValidationError(
                "Из письма можно применить только события «отправлен» и «на складе»; "
                "остальное меняется в карточке заказа"
            )
        numbers = [normalize_tracking_number(raw) for raw in tracking_numbers or []]
        numbers = [n for n in numbers if n]
        async with self._uow:
            # Авторитетная перепроверка под row-lock: если воркер разобрал письмо,
            # пока пользователь заполнял форму, повторно не применяем.
            locked = await self._emails.get(email_id, for_update=True)
            if locked is None:
                raise NotFoundError.entity("Письмо", email_id)
            if locked.processing_status == EmailProcessingStatus.PROCESSED:
                raise ConflictError(
                    "Письмо уже разобрано — повторный разбор задублирует события"
                )
            for number in numbers:
                existing = await self._tracks.get_by_number(number)
                details: dict = {"tracking_number": number, "resolved_manually": True}
                if existing is None:
                    await self._tracks.add(
                        tracking_number=number,
                        carrier=carrier,
                        order_id=order_id,
                        source=TrackSource.EMAIL,
                        email_log_id=email_id,
                        match_status=TrackMatchStatus.LINKED,
                        candidates=None,
                        note=None,
                    )
                else:
                    if existing.order_id is not None and existing.order_id != order_id:
                        # человек сознательно перевешивает трек — фиксируем в ленте
                        details["relinked_from_order"] = existing.order_id
                    await self._tracks.update(
                        existing.id,
                        {
                            "order_id": order_id,
                            "match_status": TrackMatchStatus.LINKED,
                            "resolved_at": _now(),
                            "candidates": None,
                        },
                    )
                await self._emails.add_event(
                    email_id=email_id,
                    event_type=event_type,
                    order_id=order_id,
                    action=EmailAction.TRACK_ADDED,
                    details=details,
                )

            if event_type is not None:
                target = (
                    OrderStatus.SHIPPED
                    if event_type == EmailEventType.SHIPPED
                    else OrderStatus.AT_WAREHOUSE
                )
                outcome = await self._order_service.advance_status_auto(
                    order_id, target, email_log_id=email_id, source=StatusSource.MANUAL
                )
                action = {
                    "advanced": EmailAction.STATUS_ADVANCED,
                    "stale": EmailAction.IGNORED_STALE,
                    "terminal": EmailAction.IGNORED_TERMINAL,
                }.get(outcome, EmailAction.INFO)
                await self._emails.add_event(
                    email_id=email_id,
                    event_type=event_type,
                    order_id=order_id,
                    action=action,
                    details={"outcome": outcome, "resolved_manually": True},
                )
            elif not numbers:
                # ни события, ни валидных треков — просто пометка «письмо относится к заказу»
                await self._emails.add_event(
                    email_id=email_id,
                    event_type=email.event_type,
                    order_id=order_id,
                    action=EmailAction.INFO,
                    details={"resolved_manually": True},
                )

            await self._emails.update(
                email_id,
                {
                    "processing_status": EmailProcessingStatus.PROCESSED,
                    "processed_at": _now(),
                    "error": None,
                    "next_attempt_at": None,
                },
            )

    async def retry_email(self, email_id: int) -> None:
        if await self._emails.get(email_id) is None:
            raise NotFoundError.entity("Письмо", email_id)
        await self._emails.update(
            email_id,
            {
                "processing_status": EmailProcessingStatus.NEW,
                "attempts": 0,
                "next_attempt_at": None,
                "error": None,
            },
        )

    async def ignore_email(self, email_id: int) -> None:
        if await self._emails.get(email_id) is None:
            raise NotFoundError.entity("Письмо", email_id)
        await self._emails.update(
            email_id, {"processing_status": EmailProcessingStatus.IGNORED}
        )

    # ---------------- Служебное для воркера ----------------

    async def has_credentials(self) -> bool:
        creds = await self._gmail_state.get_credentials()
        return creds is not None and creds.revoked_at is None

    async def poll_interval_sec(self) -> int:
        return int(await self._setting("mail.poll_interval_sec"))

    async def record_cycle_error(self, error: str) -> None:
        state = await self._gmail_state.get_sync_state()
        await self._gmail_state.update_sync_state(
            {
                "last_poll_at": _now(),
                "last_error": error[:1000],
                "consecutive_failures": state.consecutive_failures + 1,
            }
        )

    async def consecutive_failures(self) -> int:
        return (await self._gmail_state.get_sync_state()).consecutive_failures

    # ---------------- Оффсайт-бэкапы на Google Drive ----------------

    async def drive_backup_sync(self) -> None:
        """Раз в сутки заливает свежий дамп pg_dump на Google Drive аккаунта почты.

        Никогда не ломает почтовый цикл: любые ошибки — только в лог.
        Отметка об успехе ставится после загрузки, поэтому сбой повторится
        на следующем цикле сам."""
        if self._drive is None or self._backups_dir is None:
            return
        try:
            creds = await self._gmail_state.get_credentials()
            if creds is None or creds.revoked_at is not None:
                return
            today = business_today().isoformat()
            if await self._settings.get("backup.gdrive_last_sync") == today:
                return
            dumps = sorted(self._backups_dir.glob("crm-*.sql"))
            if not dumps:
                return
            newest = dumps[-1]
            token = await self._access_token()
            folder = await self._drive.ensure_folder(token, DRIVE_BACKUP_FOLDER)
            remote = await self._drive.list_files(token, folder)
            by_name = {f["name"]: f["id"] for f in remote}
            if newest.name not in by_name:
                await self._drive.upload(token, folder, newest.name, newest.read_bytes())
                log.info("Оффсайт-бэкап: %s загружен на Google Drive", newest.name)
            # Ротация на Drive: имена crm-ГГГГММДД-… сортируются хронологически.
            names = sorted(set(by_name) | {newest.name})
            for name in names[:-DRIVE_BACKUP_KEEP]:
                if name in by_name:
                    await self._drive.delete(token, by_name[name])
            async with self._uow:
                await self._settings.set_many({"backup.gdrive_last_sync": today})
        except DriveScopeError:
            log.warning(
                "Оффсайт-бэкап: у токена нет прав Google Drive — переподключите "
                "Gmail в настройках, чтобы выдать доступ"
            )
        except Exception:  # noqa: BLE001 — бэкап не должен ронять цикл
            log.exception("Оффсайт-бэкап на Google Drive не удался")

    async def _allowed_domains(self) -> list[str]:
        whitelist = await self._setting("mail.whitelist_domains") or []
        forwarders = await self._setting("mail.forwarder_domains") or []
        return [*whitelist, *forwarders]

    async def _setting(self, key: str):
        value = await self._settings.get(key)
        return DEFAULTS.get(key) if value is None else value


def _now() -> datetime:
    return datetime.now(UTC)
