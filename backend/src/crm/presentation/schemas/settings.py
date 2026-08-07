from __future__ import annotations

from pydantic import BaseModel, Field


class GmailConnectionOut(BaseModel):
    connected: bool
    email: str | None
    needs_reauth: bool


class SettingsOut(BaseModel):
    llm_model: str
    llm_enabled: bool
    llm_auto_min_confidence: float
    poll_interval_sec: int
    backfill_days: int
    whitelist_domains: list[str]
    forwarder_domains: list[str]
    gmail_query: str
    auto_threshold: int
    suggest_threshold: int
    gmail: GmailConnectionOut


class SettingsPatch(BaseModel):
    llm_model: str | None = Field(default=None, min_length=1)
    llm_enabled: bool | None = None
    llm_auto_min_confidence: float | None = Field(default=None, ge=0, le=1)
    poll_interval_sec: int | None = Field(default=None, ge=30, le=3600)
    backfill_days: int | None = Field(default=None, ge=1, le=365)
    whitelist_domains: list[str] | None = None
    forwarder_domains: list[str] | None = None
    gmail_query: str | None = None
    auto_threshold: int | None = Field(default=None, ge=1, le=1000)
    suggest_threshold: int | None = Field(default=None, ge=0, le=1000)


class LlmTestOut(BaseModel):
    ok: bool
    model: str | None
    message: str
