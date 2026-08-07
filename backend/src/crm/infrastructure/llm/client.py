"""LLM-клиент для OpenRouter (OpenAI-совместимый /chat/completions).

- модель читается из app_settings на каждый вызов (смена без рестарта);
- structured output через response_format json_schema, при неподдержке — json_object;
- ретраи с экспоненциальным backoff на 429/5xx/таймауты;
- repair-цикл: невалидный JSON -> сообщение об ошибке валидации -> повторный запрос;
- учёт токенов и стоимости (usage.include).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crm.application.interfaces.llm import LLMUnavailableError, LLMValidationError
from crm.application.interfaces.repositories import SettingsRepository
from crm.domain.enums import EmailEventType
from crm.domain.models import EmailExtraction, ExtractedTrack, LLMUsage
from crm.infrastructure.llm.prompt import build_system_prompt

log = logging.getLogger("crm.llm")

DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
_TIMEOUT = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)


class _TrackingNumberModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: str
    carrier: str | None = None


class _ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reasoning: str = ""
    event_type: Literal[
        "order_confirmation",
        "shipped",
        "arrived_at_warehouse",
        "delivery_update",
        "cancellation_or_refund",
        "other",
    ]
    confidence: float = Field(ge=0, le=1)
    store_domain: str | None = None
    order_number: str | None = None
    tracking_numbers: list[_TrackingNumberModel] = Field(default_factory=list)
    carrier: str | None = None
    summary: str = ""


JSON_SCHEMA = {
    "name": "email_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "reasoning",
            "event_type",
            "confidence",
            "store_domain",
            "order_number",
            "tracking_numbers",
            "carrier",
            "summary",
        ],
        "properties": {
            # reasoning идёт первым: модель сначала рассуждает, потом классифицирует
            "reasoning": {
                "type": "string",
                "description": "1–2 коротких предложения по-русски: почему выбран "
                "event_type и откуда взяты номера",
            },
            "event_type": {
                "type": "string",
                "enum": [
                    "order_confirmation",
                    "shipped",
                    "arrived_at_warehouse",
                    "delivery_update",
                    "cancellation_or_refund",
                    "other",
                ],
                "description": "Тип события письма (см. определения в инструкции)",
            },
            "confidence": {
                "type": "number",
                "description": "Уверенность именно в event_type, от 0 до 1; не завышать",
            },
            "store_domain": {
                "type": ["string", "null"],
                "description": "Домен магазина (amazon.com); null, если магазин не назван",
            },
            "order_number": {
                "type": ["string", "null"],
                "description": "Номер заказа у магазина в исходном формате; НЕ трек-номер",
            },
            "tracking_numbers": {
                "type": "array",
                "description": "Только номера, буквально присутствующие в письме или его ссылках",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["number", "carrier"],
                    "properties": {
                        "number": {"type": "string"},
                        "carrier": {
                            "type": ["string", "null"],
                            "enum": [
                                "ups", "usps", "fedex", "dhl", "amazon_logistics", "other", None,
                            ],
                        },
                    },
                },
            },
            "carrier": {
                "type": ["string", "null"],
                "enum": ["ups", "usps", "fedex", "dhl", "amazon_logistics", "other", None],
                "description": "Основной перевозчик письма, если однозначен",
            },
            "summary": {
                "type": "string",
                "description": "Одна короткая фраза по-русски для ленты событий CRM",
            },
        },
    },
}


class OpenRouterLLM:
    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: SettingsRepository,
        *,
        api_key: str,
        base_url: str,
    ) -> None:
        self._http = http
        self._settings = settings
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def extract(
        self,
        *,
        from_addr: str,
        subject: str | None,
        sent_at: datetime | None,
        body_text: str,
    ) -> tuple[EmailExtraction, LLMUsage]:
        if not await self._enabled():
            raise LLMUnavailableError("LLM выключен в настройках")
        model = await self._model()
        max_validation = int(await self._setting("llm.max_validation_attempts", 2))

        # Контекст из настроек: известные отправители и домены склада-форвардера —
        # ключ к различению «перевозчик доставил» и «посылка на складе».
        system_prompt = build_system_prompt(
            store_domains=list(await self._setting("mail.whitelist_domains", []) or []),
            forwarder_domains=list(await self._setting("mail.forwarder_domains", []) or []),
        )
        user = (
            f"From: {from_addr}\n"
            f"Subject: {subject or ''}\n"
            f"Date: {sent_at.isoformat() if sent_at else ''}\n\n"
            f"{body_text[:15000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ]

        attempts = 0
        prompt_tokens = completion_tokens = 0
        cost = Decimal("0")
        last_error: Exception | None = None

        for _ in range(max_validation + 1):
            content, usage = await self._complete(model, messages)
            attempts += 1
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            if usage.get("cost") is not None:
                cost += Decimal(str(usage["cost"]))
            try:
                # content может быть None (глюк провайдера) — TypeError уводит в repair
                parsed = _ExtractionModel.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                last_error = exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": content or ""},
                    {
                        "role": "user",
                        "content": (
                            f"Ответ не прошёл валидацию: {exc}. "
                            "Верни исправленный JSON строго по схеме, без пояснений."
                        ),
                    },
                ]
                continue
            extraction = EmailExtraction(
                event_type=EmailEventType(parsed.event_type),
                confidence=parsed.confidence,
                store_domain=parsed.store_domain,
                order_number=parsed.order_number,
                tracking_numbers=[
                    ExtractedTrack(number=t.number, carrier=t.carrier)
                    for t in parsed.tracking_numbers
                ],
                carrier=parsed.carrier,
                summary=parsed.summary,
                reasoning=parsed.reasoning or None,
            )
            usage_total = LLMUsage(
                model=model,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
                cost_usd=cost if cost else None,
                attempts=attempts,
            )
            return extraction, usage_total

        raise LLMValidationError(f"Модель {model} возвращает невалидный JSON: {last_error}")

    async def ping(self) -> str:
        model = await self._model()
        await self._complete(
            model,
            [{"role": "user", "content": "Ответь одним словом: ok"}],
            structured=False,
            max_tokens=8,
        )
        return model

    # ---------- HTTP с ретраями ----------

    async def _complete(
        self,
        model: str,
        messages: list[dict],
        *,
        structured: bool = True,
        max_tokens: int = 1024,
    ) -> tuple[str, dict]:
        max_http = max(int(await self._setting("llm.max_http_attempts", 3)), 1)
        use_json_schema = True
        last_reason = "неизвестная ошибка"
        attempt = 0

        while attempt < max_http:
            body: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
                "usage": {"include": True},
            }
            if structured:
                if use_json_schema:
                    body["response_format"] = {"type": "json_schema", "json_schema": JSON_SCHEMA}
                else:
                    body["response_format"] = {"type": "json_object"}
            try:
                resp = await self._http.post(
                    f"{self._base_url}/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "X-Title": "shaprivezu",
                    },
                    timeout=_TIMEOUT,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_reason = f"сеть: {exc.__class__.__name__}"
                attempt += 1
                if attempt < max_http:
                    await self._backoff(attempt - 1)
                continue

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                # Retry-After ограничиваем: провайдер может прислать час
                delay = (
                    min(float(retry_after), 60.0)
                    if retry_after and retry_after.isdigit()
                    else None
                )
                last_reason = "429 rate limit"
                attempt += 1
                if attempt < max_http:
                    await self._backoff(attempt - 1, override=delay)
                continue
            if resp.status_code >= 500:
                last_reason = f"HTTP {resp.status_code}"
                attempt += 1
                if attempt < max_http:
                    await self._backoff(attempt - 1)
                continue
            if resp.status_code == 400 and structured and use_json_schema:
                text = resp.text.lower()
                if "response_format" in text or "json_schema" in text or "schema" in text:
                    # модель не поддерживает json_schema — деградация до json_object,
                    # схема дописывается в текущий system-промпт (не теряя контекста).
                    # Попытку НЕ сжигаем: это переговоры о формате, а не сбой —
                    # иначе при max_http_attempts=1 фолбэк был бы недостижим.
                    use_json_schema = False
                    last_reason = "модель не поддерживает json_schema"
                    system_content = next(
                        (m["content"] for m in messages if m["role"] == "system"), ""
                    )
                    messages = [
                        {
                            "role": "system",
                            "content": system_content
                            + "\n\nСхема ответа (обязательна):\n"
                            + json.dumps(JSON_SCHEMA["schema"], ensure_ascii=False),
                        },
                        *[m for m in messages if m["role"] != "system"],
                    ]
                    continue
            if resp.status_code >= 400:
                # Прочие 4xx (битый слаг модели, ключ, эндпоинт) — ошибка КОНФИГУРАЦИИ,
                # не вина письма: письма остаются в pending_llm, а не в manual_review.
                raise LLMUnavailableError(
                    f"OpenRouter: HTTP {resp.status_code} — {resp.text[:300]}"
                )

            try:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMUnavailableError(
                    f"Неожиданный ответ OpenRouter: {resp.text[:300]}"
                ) from exc
            return content, data.get("usage") or {}

        raise LLMUnavailableError(f"OpenRouter недоступен после {max_http} попыток ({last_reason})")

    @staticmethod
    async def _backoff(attempt: int, override: float | None = None) -> None:
        delay = override if override is not None else min(2**attempt, 8) + random.random()
        await asyncio.sleep(delay)

    async def _model(self) -> str:
        return await self._setting("llm.model", DEFAULT_MODEL)

    async def _enabled(self) -> bool:
        return bool(await self._setting("llm.enabled", True))

    async def _setting(self, key: str, default):
        value = await self._settings.get(key)
        return default if value is None else value


class NullLLM:
    """Без ключа: письма честно копятся в pending_llm, воркер жив."""

    async def extract(self, **kwargs) -> tuple[EmailExtraction, LLMUsage]:
        raise LLMUnavailableError("OPENROUTER_API_KEY не задан")

    async def ping(self) -> str:
        raise LLMUnavailableError("OPENROUTER_API_KEY не задан")
