"""Ingest-фаза: курсор по записям истории, бэклог больше лимита, удалённые письма."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crm.application.interfaces.gmail import (
    GmailProfile,
    HistoryPage,
    HistoryRecord,
    MessagesPage,
)
from crm.application.services import mail_service as ms
from crm.application.services.mail_service import MailService
from crm.application.services.matching import MatcherService
from crm.domain.enums import EmailProcessingStatus
from crm.domain.models import EmailMessage, GmailCredentials
from tests.unit.fakes import (
    NOW,
    FakeEmailRepository,
    FakeGmailStateRepository,
    FakeOrderRepository,
    FakeSettingsRepository,
    FakeSuborderRepository,
    FakeTrackRepository,
    FakeUnitOfWork,
)


class FakeGmail:
    def __init__(
        self,
        records: list[HistoryRecord] | None = None,
        messages: dict[str, EmailMessage | None] | None = None,
        mailbox_history_id: int = 999,
    ) -> None:
        self.records = records or []
        self.messages = messages or {}
        self.mailbox_history_id = mailbox_history_id

    def build_auth_url(self, state: str) -> str:
        return "https://accounts.google.com/auth"

    async def exchange_code(self, code):
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token):
        raise NotImplementedError

    async def get_profile(self, token) -> GmailProfile:
        return GmailProfile(email="x@gmail.com", history_id=self.mailbox_history_id)

    async def list_history(self, token, start_history_id, page_token=None) -> HistoryPage:
        return HistoryPage(
            records=[r for r in self.records if r.id > start_history_id],
            next_page_token=None,
            mailbox_history_id=self.mailbox_history_id,
        )

    async def list_messages(self, token, query=None, page_token=None, max_results=100):
        return MessagesPage(message_ids=list(self.messages.keys()), next_page_token=None)

    async def get_message(self, token, message_id) -> EmailMessage | None:
        return self.messages.get(message_id)


def make_msg(mid: str, domain: str = "amazon.com") -> EmailMessage:
    return EmailMessage(
        gmail_message_id=mid,
        gmail_thread_id=None,
        message_id_hdr=f"<{mid}@x>",
        from_addr=f"noreply@{domain}",
        from_domain=domain,
        subject="Order update",
        sent_at=NOW,
        snippet=None,
        body_text="body",
    )


@pytest.fixture
def state() -> FakeGmailStateRepository:
    st = FakeGmailStateRepository()
    st.credentials = GmailCredentials(
        email_address="x@gmail.com",
        refresh_token="rt",
        access_token="at",
        access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=None,
    )
    return st


def build_service(gmail: FakeGmail, state: FakeGmailStateRepository, emails: FakeEmailRepository):
    return MailService(
        gmail=gmail,
        gmail_state=state,
        emails=emails,
        settings=FakeSettingsRepository({"mail.whitelist_domains": ["amazon.com"]}),
        orders=FakeOrderRepository(),
        tracks=FakeTrackRepository(),
        suborders=FakeSuborderRepository(),
        order_service=None,
        matcher=MatcherService(),
        llm=None,
        uow=FakeUnitOfWork(),
        gmail_configured=True,
    )


async def test_backlog_beyond_limit_does_not_lose_emails(state, monkeypatch):
    """Критичный сценарий: 5 писем при лимите 2 на цикл — курсор идёт по записям,
    все письма добираются за несколько циклов, ничего не теряется."""
    monkeypatch.setattr(ms, "MAX_INGEST_PER_CYCLE", 2)
    records = [HistoryRecord(id=100 + i, message_ids=[f"m{i}"]) for i in range(1, 6)]
    gmail = FakeGmail(records, {f"m{i}": make_msg(f"m{i}") for i in range(1, 6)})
    emails = FakeEmailRepository()
    state.sync_state = state.sync_state.__class__(
        history_id=100,
        last_poll_at=None,
        last_success_at=None,
        last_error=None,
        consecutive_failures=0,
        llm_degraded=False,
    )
    svc = build_service(gmail, state, emails)

    assert await svc.ingest_cycle() == 2
    assert state.sync_state.history_id == 102  # последняя обработанная запись, не хвост ящика

    assert await svc.ingest_cycle() == 2
    assert state.sync_state.history_id == 104

    assert await svc.ingest_cycle() == 1
    assert state.sync_state.history_id == 999  # всё дочитано — прыжок на текущий id ящика

    assert len(emails.storage) == 5
    # повторный цикл ничего не дублирует
    assert await svc.ingest_cycle() == 0


async def test_deleted_message_does_not_block_cycle(state):
    """Письмо удалили до скачивания (404 -> None) — цикл не падает, курсор двигается."""
    records = [HistoryRecord(id=101, message_ids=["gone", "ok"])]
    gmail = FakeGmail(records, {"gone": None, "ok": make_msg("ok")})
    emails = FakeEmailRepository()
    state.sync_state = state.sync_state.__class__(
        history_id=100,
        last_poll_at=None,
        last_success_at=None,
        last_error=None,
        consecutive_failures=0,
        llm_degraded=False,
    )
    svc = build_service(gmail, state, emails)

    assert await svc.ingest_cycle() == 1
    assert state.sync_state.history_id == 999
    assert state.sync_state.last_success_at is not None


async def test_initial_sync_prefilters_by_whitelist(state):
    """Первый запуск: не-whitelist домен уходит в filtered, письмо не теряется."""
    gmail = FakeGmail(
        messages={"a": make_msg("a"), "b": make_msg("b", domain="spam.example")}
    )
    emails = FakeEmailRepository()
    svc = build_service(gmail, state, emails)  # history_id = None -> initial sync

    assert await svc.ingest_cycle() == 2
    statuses = {e.gmail_message_id: e.processing_status for e in emails.storage.values()}
    assert statuses["a"] == EmailProcessingStatus.NEW
    assert statuses["b"] == EmailProcessingStatus.FILTERED
    assert state.sync_state.history_id == 999
