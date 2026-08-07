from __future__ import annotations

from fastapi import Request

from crm.domain.exceptions import AuthenticationError

SESSION_COOKIE = "crm_session"


def require_auth(request: Request) -> None:
    auth = request.app.state.auth_service
    token = request.cookies.get(SESSION_COOKIE)
    if not auth.verify_token(token):
        raise AuthenticationError()
