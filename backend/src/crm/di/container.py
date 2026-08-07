from __future__ import annotations

from dishka import AsyncContainer, make_async_container

from crm.di.providers import AppProvider, RequestProvider
from crm.infrastructure.config import Settings


def make_container(settings: Settings) -> AsyncContainer:
    return make_async_container(AppProvider(settings), RequestProvider())
