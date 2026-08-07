from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from crm.domain.exceptions import AuthenticationError
from crm.presentation.auth import SESSION_COOKIE, require_auth
from crm.presentation.schemas.auth import LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Единственный пользователь: глобальный лимит попыток достаточен
LOGIN_WINDOW_SEC = 900
LOGIN_MAX_FAILS = 10


@router.post("/login", status_code=204)
async def login(payload: LoginIn, request: Request, response: Response) -> None:
    fails: list[float] = request.app.state.login_fails
    now = time.time()
    fails[:] = [t for t in fails if now - t < LOGIN_WINDOW_SEC]
    if len(fails) >= LOGIN_MAX_FAILS:
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток входа — подождите 15 минут",
        )

    auth = request.app.state.auth_service
    if not auth.verify_password(payload.password):
        fails.append(now)
        raise AuthenticationError("Неверный пароль")

    fails.clear()
    response.set_cookie(
        SESSION_COOKIE,
        auth.issue_token(),
        max_age=auth.ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
        path="/",
    )


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", status_code=204, dependencies=[Depends(require_auth)])
async def me() -> None:
    return None
