from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crm.domain.models import EmailMessage


class GmailAuthError(Exception):
    """invalid_grant / 401: refresh token отозван, нужна повторная авторизация."""


class GmailHistoryExpiredError(Exception):
    """historyId протух (HTTP 404 на history.list) — нужен ресинк через messages.list."""


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True, slots=True)
class GmailProfile:
    email: str
    history_id: int


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    """Одна запись истории: её id — валидный курсор для startHistoryId."""

    id: int
    message_ids: list[str]


@dataclass(frozen=True, slots=True)
class HistoryPage:
    records: list[HistoryRecord]
    next_page_token: str | None
    mailbox_history_id: int | None  # текущий historyId всего ящика (НЕ «докуда дочитали»)


@dataclass(frozen=True, slots=True)
class MessagesPage:
    message_ids: list[str]
    next_page_token: str | None


class GmailPort(Protocol):
    def build_auth_url(self, state: str) -> str: ...

    async def exchange_code(self, code: str) -> OAuthTokens: ...

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens: ...

    async def get_profile(self, access_token: str) -> GmailProfile: ...

    async def list_history(
        self, access_token: str, start_history_id: int, page_token: str | None = None
    ) -> HistoryPage: ...

    async def list_messages(
        self,
        access_token: str,
        query: str | None = None,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> MessagesPage: ...

    async def get_message(self, access_token: str, message_id: str) -> EmailMessage | None:
        """None, если письмо уже удалено из ящика (404) — пропускаем, не ломая цикл."""
        ...
