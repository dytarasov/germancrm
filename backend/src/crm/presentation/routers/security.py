from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.services.security_service import SecurityService
from crm.presentation.auth import require_auth
from crm.presentation.schemas.security import LoginBanOut

router = APIRouter(
    prefix="/api/security",
    tags=["security"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("/bans", response_model=list[LoginBanOut])
async def list_bans(svc: FromDishka[SecurityService]) -> list[LoginBanOut]:
    return [
        LoginBanOut(
            ip=b.ip,
            fails=b.fails,
            last_fail_at=b.last_fail_at,
            banned_until=b.banned_until,
        )
        for b in await svc.list_bans()
    ]


@router.delete("/bans/{ip}", status_code=204)
async def unban(ip: str, svc: FromDishka[SecurityService]) -> None:
    await svc.unban(ip)
