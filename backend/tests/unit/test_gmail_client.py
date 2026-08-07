"""Токен-эндпоинт Google: транзиентные сбои НЕ должны «отзывать» подключение."""

import httpx
import pytest

from crm.application.interfaces.gmail import GmailAuthError
from crm.infrastructure.gmail.client import GmailApiClient


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
