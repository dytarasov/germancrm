import json

import httpx
import pytest

from crm.application.interfaces.llm import LLMUnavailableError
from crm.infrastructure.llm.client import OpenRouterLLM
from tests.unit.fakes import FakeSettingsRepository

VALID_PAYLOAD = {
    "reasoning": "Письмо от Amazon с фразой shipped и трек-номером UPS.",
    "event_type": "shipped",
    "confidence": 0.92,
    "store_domain": "amazon.com",
    "order_number": "113-1234567-1234567",
    "tracking_numbers": [{"number": "1Z999AA10123456784", "carrier": "ups"}],
    "carrier": "ups",
    "summary": "Amazon отправил посылку",
}


def completion_response(content: str, cost: float = 0.004) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 90, "cost": cost},
        },
    )


def make_client(handler) -> OpenRouterLLM:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = FakeSettingsRepository({"llm.model": "anthropic/claude-haiku-4.5"})
    return OpenRouterLLM(
        http, settings, api_key="sk-test", base_url="https://openrouter.ai/api/v1"
    )


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    async def instant(*args, **kwargs):
        return None

    monkeypatch.setattr(OpenRouterLLM, "_backoff", staticmethod(instant))


async def extract(llm: OpenRouterLLM):
    return await llm.extract(
        from_addr="ship-confirm@amazon.com",
        subject="Your package has shipped",
        sent_at=None,
        body_text="Tracking: 1Z999AA10123456784, order 113-1234567-1234567",
    )


async def test_happy_path_with_usage():
    llm = make_client(lambda req: completion_response(json.dumps(VALID_PAYLOAD)))
    extraction, usage = await extract(llm)
    assert extraction.event_type == "shipped"
    assert extraction.tracking_numbers[0].number == "1Z999AA10123456784"
    assert extraction.reasoning and "Amazon" in extraction.reasoning
    assert usage.prompt_tokens == 1200
    assert usage.cost_usd is not None
    assert usage.attempts == 1


async def test_system_prompt_includes_settings_context():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["system"] = body["messages"][0]["content"]
        return completion_response(json.dumps(VALID_PAYLOAD))

    llm = make_client(handler)
    llm._settings.values["mail.forwarder_domains"] = ["mywarehouse.com"]  # noqa: SLF001
    llm._settings.values["mail.whitelist_domains"] = ["amazon.com"]  # noqa: SLF001
    await extract(llm)
    assert "mywarehouse.com" in seen["system"]
    assert "amazon.com" in seen["system"]


async def test_retry_on_429_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return completion_response(json.dumps(VALID_PAYLOAD))

    extraction, _ = await extract(make_client(handler))
    assert calls["n"] == 2
    assert extraction.event_type == "shipped"


async def test_repair_cycle_on_invalid_json():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return completion_response("это не json")
        body = json.loads(request.content)
        # repair-запрос должен содержать сообщение об ошибке валидации
        assert any("не прошёл валидацию" in str(m.get("content", "")) for m in body["messages"])
        return completion_response(json.dumps(VALID_PAYLOAD))

    extraction, usage = await extract(make_client(handler))
    assert calls["n"] == 2
    assert usage.attempts == 2
    assert extraction.summary == "Amazon отправил посылку"


async def test_401_raises_unavailable_without_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(LLMUnavailableError):
        await extract(make_client(handler))
    assert calls["n"] == 1


async def test_5xx_exhausts_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(502)

    with pytest.raises(LLMUnavailableError):
        await extract(make_client(handler))
    assert calls["n"] == 3  # llm.max_http_attempts по умолчанию


async def test_fallback_works_even_with_single_attempt():
    """Деградация json_schema→json_object — переговоры о формате, не сбой:
    не должна сжигать HTTP-попытку даже при max_http_attempts=1."""
    calls = {"formats": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        fmt = body.get("response_format", {}).get("type")
        calls["formats"].append(fmt)
        if fmt == "json_schema":
            return httpx.Response(400, json={"error": "response_format not supported"})
        return completion_response(json.dumps(VALID_PAYLOAD))

    llm = make_client(handler)
    llm._settings.values["llm.max_http_attempts"] = 1  # noqa: SLF001
    extraction, _ = await extract(llm)
    assert calls["formats"] == ["json_schema", "json_object"]
    assert extraction.event_type == "shipped"


async def test_json_schema_fallback_to_json_object():
    calls = {"n": 0, "formats": []}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content)
        calls["formats"].append(body.get("response_format", {}).get("type"))
        if body.get("response_format", {}).get("type") == "json_schema":
            return httpx.Response(400, json={"error": "response_format not supported"})
        return completion_response(json.dumps(VALID_PAYLOAD))

    extraction, _ = await extract(make_client(handler))
    assert calls["formats"] == ["json_schema", "json_object"]
    assert extraction.event_type == "shipped"


async def test_bad_model_slug_is_unavailable_not_manual_review():
    """Опечатка в слаге модели — ошибка конфигурации: письма должны остаться
    в pending_llm (LLMUnavailable), а не осушаться в manual_review."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "not a valid model ID"}})

    with pytest.raises(LLMUnavailableError):
        await extract(make_client(handler))
    assert calls["n"] == 1  # без ретраев — это не транзиентная ошибка


async def test_null_content_goes_to_repair_not_crash():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": None}}], "usage": {}},
            )
        return completion_response(json.dumps(VALID_PAYLOAD))

    extraction, _ = await extract(make_client(handler))
    assert calls["n"] == 2
    assert extraction.event_type == "shipped"


async def test_disabled_llm_is_unavailable():
    llm = make_client(lambda req: completion_response(json.dumps(VALID_PAYLOAD)))
    llm._settings.values["llm.enabled"] = False  # noqa: SLF001 — прямое управление фейком
    with pytest.raises(LLMUnavailableError):
        await extract(llm)


def test_strip_fences_variants():
    """json_object-режим: модель заворачивает JSON в fence или предисловие."""
    from crm.infrastructure.llm.client import _strip_fences

    clean = '{"a": 1}'
    assert _strip_fences(clean) == clean
    assert _strip_fences('```json\n{"a": 1}\n```') == clean
    assert _strip_fences('Вот JSON:\n{"a": 1}\nГотово.') == clean
    assert _strip_fences(None) is None
    assert _strip_fences("совсем не json") == "совсем не json"


def test_schema_has_no_nullable_enum_unions():
    """Anthropic-провайдеры отдают 400 на enum при type: ["string","null"] —
    nullable enum допустим только через anyOf."""
    from crm.infrastructure.llm.client import JSON_SCHEMA

    def walk(node):
        if isinstance(node, dict):
            if "enum" in node and isinstance(node.get("type"), list):
                raise AssertionError(f"nullable enum без anyOf: {node}")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(JSON_SCHEMA)
