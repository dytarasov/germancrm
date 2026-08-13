"""Gmail REST API v1 напрямую через httpx: token refresh, profile, messages, history.

Сознательно без google-api-python-client: нужно 5 вызовов, format=full отдаёт
уже разобранное MIME-дерево.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from email.utils import parseaddr
from urllib.parse import urlencode

import httpx
from selectolax.parser import HTMLParser

from crm.application.interfaces.gmail import (
    GmailAuthError,
    GmailHistoryExpiredError,
    GmailProfile,
    HistoryPage,
    HistoryRecord,
    MessagesPage,
    OAuthTokens,
)
from crm.domain.models import EmailMessage

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
# drive.file — для оффсайт-бэкапов: приложение видит на Drive только свои файлы
SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/drive.file"
)

BODY_TEXT_LIMIT = 15_000
# Треки часто живут только в href — блоку ссылок гарантируется место в лимите,
# иначе длинное маркетинговое письмо вытеснит его за срез BODY_TEXT_LIMIT.
LINKS_BLOCK_LIMIT = 5_000
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class GmailApiClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    # ---------- OAuth ----------

    def build_auth_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        data = await self._token_request(
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        data = await self._token_request(
            {
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            }
        )
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=None,
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def _token_request(self, form: dict[str, str]) -> dict:
        resp = await self._http.post(TOKEN_URL, data=form, timeout=_TIMEOUT)
        # 5xx/429 — транзиентные сбои Google: НЕ auth-ошибка, иначе рабочий
        # refresh token будет ошибочно помечен отозванным.
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        if resp.status_code >= 400:
            body = resp.text[:500]
            raise GmailAuthError(f"Google OAuth {resp.status_code}: {body}")
        return resp.json()

    # ---------- API ----------

    async def get_profile(self, access_token: str) -> GmailProfile:
        data = await self._get(access_token, f"{API_BASE}/profile")
        return GmailProfile(email=data["emailAddress"], history_id=int(data["historyId"]))

    async def list_history(
        self, access_token: str, start_history_id: int, page_token: str | None = None
    ) -> HistoryPage:
        params: dict[str, str] = {
            "startHistoryId": str(start_history_id),
            "historyTypes": "messageAdded",
            # как и messages.list, не тащим СПАМ/корзину — иначе поддельный From
            # из спама попадал бы в конвейер
            "labelId": "INBOX",
            "maxResults": "100",
        }
        if page_token:
            params["pageToken"] = page_token
        data = await self._get(access_token, f"{API_BASE}/history", params=params)
        records: list[HistoryRecord] = []
        seen: set[str] = set()
        for h in data.get("history", []):
            ids: list[str] = []
            for added in h.get("messagesAdded", []):
                mid = added.get("message", {}).get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
            # пустые записи тоже нужны: их id двигает курсор
            records.append(HistoryRecord(id=int(h["id"]), message_ids=ids))
        history_id = data.get("historyId")
        return HistoryPage(
            records=records,
            next_page_token=data.get("nextPageToken"),
            mailbox_history_id=int(history_id) if history_id else None,
        )

    async def list_messages(
        self,
        access_token: str,
        query: str | None = None,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> MessagesPage:
        params: dict[str, str] = {"maxResults": str(max_results)}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        data = await self._get(access_token, f"{API_BASE}/messages", params=params)
        return MessagesPage(
            message_ids=[m["id"] for m in data.get("messages", [])],
            next_page_token=data.get("nextPageToken"),
        )

    async def get_message(self, access_token: str, message_id: str) -> EmailMessage | None:
        try:
            data = await self._get(
                access_token, f"{API_BASE}/messages/{message_id}", params={"format": "full"}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # письмо удалили раньше, чем мы его скачали — не стопорим ingest
                return None
            raise
        return parse_gmail_message(data)

    async def _get(self, access_token: str, url: str, params: dict | None = None) -> dict:
        resp = await self._http.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            raise GmailAuthError("Gmail API: 401 (токен недействителен)")
        if resp.status_code == 404 and "/history" in url:
            raise GmailHistoryExpiredError()
        resp.raise_for_status()
        return resp.json()


# ---------- Разбор письма ----------


def parse_gmail_message(data: dict) -> EmailMessage:
    payload = data.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    _, from_email = parseaddr(headers.get("from", ""))
    from_domain = from_email.rsplit("@", 1)[-1].lower() if "@" in from_email else ""

    internal_ms = data.get("internalDate")
    sent_at = (
        datetime.fromtimestamp(int(internal_ms) / 1000, tz=UTC) if internal_ms else None
    )

    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_parts(payload, plain_parts, html_parts)
    # Треки часто лежат только в ссылках HTML-версии («Track package»),
    # поэтому href-ы добавляем к тексту всегда.
    links = _extract_links("\n".join(html_parts)) if html_parts else []
    if plain_parts:
        body_text = "\n".join(plain_parts)
    else:
        body_text, _ = _html_to_text("\n".join(html_parts))

    # Блок ссылок собираем в свой лимит и НЕ даём длинному телу вытеснить его
    # за общий срез: обрезается основной текст, ссылки сохраняются целиком.
    links_block = ""
    if links:
        joined: list[str] = []
        used = 0
        for href in links:
            if used + len(href) + 1 > LINKS_BLOCK_LIMIT:
                break
            joined.append(href)
            used += len(href) + 1
        if joined:
            links_block = "\n\nСсылки из письма:\n" + "\n".join(joined)
    if body_text or links_block:
        body_text = body_text[: BODY_TEXT_LIMIT - len(links_block)] + links_block

    return EmailMessage(
        gmail_message_id=data["id"],
        gmail_thread_id=data.get("threadId"),
        message_id_hdr=headers.get("message-id"),
        from_addr=from_email or headers.get("from", ""),
        from_domain=from_domain,
        subject=headers.get("subject"),
        sent_at=sent_at,
        snippet=data.get("snippet"),
        body_text=body_text or None,
    )


def _collect_parts(part: dict, plain: list[str], html: list[str]) -> None:
    mime = part.get("mimeType", "")
    body_data = part.get("body", {}).get("data")
    if body_data:
        decoded = _b64url_decode(body_data)
        if mime == "text/plain":
            plain.append(decoded)
        elif mime == "text/html":
            html.append(decoded)
    for child in part.get("parts", []) or []:
        _collect_parts(child, plain, html)


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> tuple[str, list[str]]:
    if not html:
        return "", []
    tree = HTMLParser(html)
    for tag in ("script", "style"):
        for node in tree.css(tag):
            node.decompose()
    text = tree.body.text(separator=" ") if tree.body else tree.text(separator=" ")
    return " ".join(text.split()), _extract_links(html)


def _extract_links(html: str) -> list[str]:
    if not html:
        return []
    tree = HTMLParser(html)
    links: list[str] = []
    seen: set[str] = set()
    for node in tree.css("a"):
        href = (node.attributes or {}).get("href")
        if href and href.startswith("http") and href not in seen:
            seen.add(href)
            links.append(href)
    return links
