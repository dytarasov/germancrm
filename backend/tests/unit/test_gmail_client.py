"""Токен-эндпоинт Google (транзиентные сбои НЕ должны «отзывать» подключение)
и парсер писем (треки, живущие только в ссылках HTML)."""

import base64

import httpx
import pytest

from crm.application.interfaces.gmail import GmailAuthError
from crm.infrastructure.gmail.client import (
    BODY_TEXT_LIMIT,
    GmailApiClient,
    parse_gmail_message,
)


def make_client(handler) -> GmailApiClient:
    return GmailApiClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        client_id="cid",
        client_secret="secret",
        redirect_uri="http://localhost:8000/cb",
    )


async def test_transient_5xx_is_not_auth_error():
    client = make_client(lambda req: httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(httpx.HTTPStatusError):
        await client.refresh_access_token("rt")


async def test_rate_limit_is_not_auth_error():
    client = make_client(lambda req: httpx.Response(429, text="rate limited"))
    with pytest.raises(httpx.HTTPStatusError):
        await client.refresh_access_token("rt")


async def test_invalid_grant_is_auth_error():
    client = make_client(
        lambda req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(GmailAuthError):
        await client.refresh_access_token("rt")


async def test_success_returns_tokens():
    client = make_client(
        lambda req: httpx.Response(
            200, json={"access_token": "at", "expires_in": 3600}
        )
    )
    tokens = await client.refresh_access_token("rt")
    assert tokens.access_token == "at"
    assert tokens.refresh_token is None


# ---------- parse_gmail_message: треки в ссылках HTML ----------


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def _html_message(html: str, plain: str | None = None) -> dict:
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    return {
        "id": "m1",
        "internalDate": "1755000000000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Shop <noreply@shop.com>"},
                {"name": "Subject", "value": "Your order shipped"},
            ],
            "parts": parts,
        },
    }


TRACK_URL = "https://www.ups.com/track?tracknum=1Z999AA10123456784"


def test_track_only_in_link_lands_in_body():
    """Магазин шлёт кнопку «Track package» — сам трек только в href."""
    msg = parse_gmail_message(
        _html_message(f'<p>Order on its way!</p><a href="{TRACK_URL}">Track package</a>')
    )
    assert TRACK_URL in (msg.body_text or "")


def test_links_survive_body_limit():
    """Длинная маркетинговая простыня не должна вытеснять блок ссылок за срез."""
    long_plain = "покупайте наши товары " * 2000  # сильно больше BODY_TEXT_LIMIT
    msg = parse_gmail_message(
        _html_message(
            f'<a href="{TRACK_URL}">Track</a>', plain=long_plain
        )
    )
    assert msg.body_text is not None
    assert len(msg.body_text) <= BODY_TEXT_LIMIT
    assert TRACK_URL in msg.body_text  # ссылка уцелела, обрезался текст
