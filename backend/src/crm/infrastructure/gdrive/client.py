"""Google Drive API v3 напрямую через httpx — только то, что нужно оффсайт-бэкапам:
папка, список файлов, загрузка, удаление. Токен — тот же OAuth, что и Gmail
(scope drive.file: приложение видит только созданные им же файлы)."""

from __future__ import annotations

import json
import uuid

import httpx

from crm.application.interfaces.gdrive import DriveScopeError

DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=120.0, pool=5.0)
_FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def ensure_folder(self, access_token: str, name: str) -> str:
        safe = name.replace("\\", "\\\\").replace("'", "\\'")
        found = await self._request(
            access_token,
            "GET",
            f"{DRIVE_API}/files",
            params={
                "q": f"name = '{safe}' and mimeType = '{_FOLDER_MIME}' and trashed = false",
                "fields": "files(id)",
            },
        )
        files = found.get("files", [])
        if files:
            return files[0]["id"]
        created = await self._request(
            access_token,
            "POST",
            f"{DRIVE_API}/files",
            json={"name": name, "mimeType": _FOLDER_MIME},
        )
        return created["id"]

    async def list_files(self, access_token: str, folder_id: str) -> list[dict]:
        data = await self._request(
            access_token,
            "GET",
            f"{DRIVE_API}/files",
            params={
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "files(id,name)",
                "pageSize": "1000",
            },
        )
        return data.get("files", [])

    async def upload(
        self, access_token: str, folder_id: str, name: str, content: bytes
    ) -> str:
        boundary = f"b{uuid.uuid4().hex}"
        meta = json.dumps({"name": name, "parents": [folder_id]})
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{meta}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--".encode()
        data = await self._request(
            access_token,
            "POST",
            f"{UPLOAD_API}?uploadType=multipart&fields=id",
            content=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
        return data["id"]

    async def delete(self, access_token: str, file_id: str) -> None:
        await self._request(access_token, "DELETE", f"{DRIVE_API}/files/{file_id}")

    async def _request(
        self,
        access_token: str,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: dict | None = None,  # noqa: A002 — локальное затенение осознанно
        content: bytes | None = None,
        headers: dict | None = None,
    ) -> dict:
        resp = await self._http.request(
            method,
            url,
            params=params,
            json=json,
            content=content,
            headers={"Authorization": f"Bearer {access_token}", **(headers or {})},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 403 and (
            "insufficient" in resp.text.lower() or "scope" in resp.text.lower()
        ):
            raise DriveScopeError(resp.text[:300])
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()
