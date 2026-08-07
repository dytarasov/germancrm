from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crm.application.interfaces.repositories import (
    EmailRepository,
    GmailStateRepository,
    SettingsRepository,
)
from crm.application.interfaces.uow import UnitOfWork

# Публичные имена полей API ↔ ключи app_settings
API_TO_KEY: dict[str, str] = {
    "llm_model": "llm.model",
    "llm_enabled": "llm.enabled",
    "llm_auto_min_confidence": "llm.auto_min_confidence",
    "poll_interval_sec": "mail.poll_interval_sec",
    "backfill_days": "mail.backfill_days",
    "whitelist_domains": "mail.whitelist_domains",
    "forwarder_domains": "mail.forwarder_domains",
    "gmail_query": "mail.gmail_query",
    "auto_threshold": "matching.auto_threshold",
    "suggest_threshold": "matching.suggest_threshold",
}

DEFAULTS: dict[str, Any] = {
    "llm.model": "anthropic/claude-haiku-4.5",
    "llm.enabled": True,
    "llm.auto_min_confidence": 0.75,
    "mail.poll_interval_sec": 180,
    "mail.backfill_days": 30,
    "mail.whitelist_domains": [],
    "mail.forwarder_domains": [],
    "mail.gmail_query": "",
    "matching.auto_threshold": 80,
    "matching.suggest_threshold": 40,
}


@dataclass(frozen=True, slots=True)
class GmailConnection:
    connected: bool
    email: str | None
    needs_reauth: bool


@dataclass(frozen=True, slots=True)
class SettingsView:
    values: dict[str, Any]  # ключи — публичные имена API
    gmail: GmailConnection


class SettingsService:
    def __init__(
        self,
        settings: SettingsRepository,
        gmail_state: GmailStateRepository,
        emails: EmailRepository,
        uow: UnitOfWork,
    ) -> None:
        self._settings = settings
        self._gmail_state = gmail_state
        self._emails = emails
        self._uow = uow

    async def view(self) -> SettingsView:
        raw = await self._settings.all()
        values = {
            api: raw.get(key, DEFAULTS.get(key)) for api, key in API_TO_KEY.items()
        }
        creds = await self._gmail_state.get_credentials()
        gmail = GmailConnection(
            connected=creds is not None and creds.revoked_at is None,
            email=creds.email_address if creds else None,
            needs_reauth=creds is not None and creds.revoked_at is not None,
        )
        return SettingsView(values=values, gmail=gmail)

    async def patch(self, values: dict[str, Any]) -> SettingsView:
        old_view = await self.view()
        mapped: dict[str, Any] = {}
        normalized_domains: dict[str, list[str]] = {}
        for api_name, value in values.items():
            key = API_TO_KEY.get(api_name)
            if key is None:
                continue
            if api_name in ("whitelist_domains", "forwarder_domains") and value is not None:
                value = sorted({str(d).strip().lower().lstrip("@") for d in value if str(d).strip()})
                normalized_domains[api_name] = value
            mapped[key] = value
        if mapped:
            async with self._uow:
                await self._settings.set_many(mapped)
                # Домен добавили в whitelist -> отфильтрованные письма этого домена
                # автоматически возвращаются в очередь обработки. Диф считаем по
                # НОРМАЛИЗОВАННЫМ значениям — иначе "@amazon.com" дал бы пустой requeue.
                for api_name, new_domains in normalized_domains.items():
                    added = set(new_domains) - set(old_view.values.get(api_name) or [])
                    for domain in added:
                        await self._emails.requeue_filtered_domain(domain)
        return await self.view()
