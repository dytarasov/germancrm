"""Порт Google Drive — ровно то, что нужно оффсайт-бэкапам."""

from __future__ import annotations

from typing import Protocol


class DriveScopeError(Exception):
    """Токену не выдан scope drive.file — нужно переподключить Gmail в настройках."""


class DrivePort(Protocol):
    async def ensure_folder(self, access_token: str, name: str) -> str: ...

    async def list_files(self, access_token: str, folder_id: str) -> list[dict]: ...

    async def upload(
        self, access_token: str, folder_id: str, name: str, content: bytes
    ) -> str: ...

    async def delete(self, access_token: str, file_id: str) -> None: ...
