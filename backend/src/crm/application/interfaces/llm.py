from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crm.domain.models import EmailExtraction, LLMUsage


class LLMUnavailableError(Exception):
    """Нет ключа / 401 / сеть недоступна после всех ретраев. Письмо остаётся в pending_llm."""


class LLMValidationError(Exception):
    """Модель стабильно возвращает невалидный ответ. Письмо уходит в manual_review."""


class LLMExtractor(Protocol):
    async def extract(
        self,
        *,
        from_addr: str,
        subject: str | None,
        sent_at: datetime | None,
        body_text: str,
    ) -> tuple[EmailExtraction, LLMUsage]: ...

    async def ping(self) -> str:
        """Тестовый вызов текущей модели; возвращает её слаг. Кидает LLMUnavailableError."""
        ...
