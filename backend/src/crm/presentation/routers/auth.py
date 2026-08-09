from __future__ import annotations

import time
from datetime import datetime

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from crm.application.services.security_service import SecurityService
from crm.domain.clock import BUSINESS_TZ
from crm.domain.exceptions import AuthenticationError
from crm.presentation.auth import SESSION_COOKIE, require_auth
from crm.presentation.ip import client_ip
from crm.presentation.schemas.auth import LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"], route_class=DishkaRoute)

# Глобальный лимит — второй эшелон: ловит в том числе запросы, у которых
# не определился публичный IP (их персональный бан не покрывает).
LOGIN_WINDOW_SEC = 900
LOGIN_MAX_FAILS = 10


def _ban_message(until: datetime) -> str:
    t = until.astimezone(BUSINESS_TZ).strftime("%d.%m %H:%M")
    return f"Слишком много неверных паролей — IP заблокирован до {t} (МСК)"


@router.post("/login", status_code=204)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    security: FromDishka[SecurityService],
) -> None:
    ip, bannable = client_ip(request)
    if bannable:
        until = await security.banned_until(ip)
        if until is not None:
            raise HTTPException(status_code=429, detail=_ban_message(until))

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
        if bannable:
            ban = await security.register_fail(ip)
            if ban.banned_until is not None:
                raise HTTPException(status_code=429, detail=_ban_message(ban.banned_until))
        raise AuthenticationError("Неверный пароль")

    fails.clear()
    if bannable:
        await security.clear(ip)
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
