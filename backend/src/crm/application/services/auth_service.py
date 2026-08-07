"""Один пользователь: пароль из env, stateless HMAC-токен в cookie (stdlib, без зависимостей)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time


class AuthService:
    def __init__(self, *, password: str, secret: str, ttl_days: int = 180) -> None:
        self._password = password
        self._secret = secret.encode()
        self.ttl_seconds = ttl_days * 86400

    def verify_password(self, password: str) -> bool:
        return secrets.compare_digest(password.encode(), self._password.encode())

    def issue_token(self) -> str:
        expires = int(time.time()) + self.ttl_seconds
        return f"{expires}.{self._sign(f'session:{expires}')}"

    def verify_token(self, token: str | None) -> bool:
        # isascii: compare_digest для str кидает TypeError на non-ASCII —
        # мусорная cookie должна давать 401, а не 500
        if not token or not token.isascii():
            return False
        expires_str, _, sig = token.partition(".")
        if not sig or not expires_str.isdigit():
            return False
        if int(expires_str) < time.time():
            return False
        return hmac.compare_digest(
            sig.encode(), self._sign(f"session:{expires_str}").encode()
        )

    # --- state для OAuth-редиректа (CSRF-защита callback'а) ---
    # Одноразовость обеспечивает presentation-слой (app.state.oauth_states).

    def issue_state(self) -> str:
        ts = str(int(time.time()))
        nonce = secrets.token_urlsafe(8)
        return f"{ts}.{nonce}.{self._sign(f'state:{ts}:{nonce}')}"

    def verify_state(self, state: str | None, max_age_seconds: int = 900) -> bool:
        if not state or not state.isascii():
            return False
        parts = state.split(".")
        if len(parts) != 3:
            return False
        ts, nonce, sig = parts
        if not sig or not ts.isdigit():
            return False
        if int(ts) + max_age_seconds < time.time():
            return False
        return hmac.compare_digest(
            sig.encode(), self._sign(f"state:{ts}:{nonce}").encode()
        )

    def _sign(self, data: str) -> str:
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()
