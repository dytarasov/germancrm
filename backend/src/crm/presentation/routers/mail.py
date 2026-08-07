from __future__ import annotations

import logging
from urllib.parse import quote

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from crm.application.services.mail_service import MailService
from crm.domain.enums import EmailEventType, EmailProcessingStatus
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import (
    email_detail_to_out,
    email_row_to_out,
    mail_event_to_out,
    mail_health_to_out,
    track_to_out,
)
from crm.presentation.schemas.dashboard import MailHealthOut
from crm.presentation.schemas.mail import (
    EmailDetailOut,
    EmailResolveIn,
    EmailRowOut,
    MailEventOut,
    MailReviewOut,
    OAuthUrlOut,
)

log = logging.getLogger("crm.mail.router")

router = APIRouter(prefix="/api/mail", tags=["mail"], route_class=DishkaRoute)

_AUTH = Depends(require_auth)


@router.get("/events", response_model=list[MailEventOut], dependencies=[_AUTH])
async def events(
    svc: FromDishka[MailService], limit: int = Query(default=50, ge=1, le=200)
) -> list[MailEventOut]:
    return [mail_event_to_out(e) for e in await svc.events(limit)]


@router.get("/review", response_model=MailReviewOut, dependencies=[_AUTH])
async def review(svc: FromDishka[MailService]) -> MailReviewOut:
    data = await svc.review()
    return MailReviewOut(
        emails=[email_row_to_out(e) for e in data.emails],
        filtered=[email_row_to_out(e) for e in data.filtered],
        open_tracks=[track_to_out(t) for t in data.open_tracks],
    )


@router.get("/emails", response_model=list[EmailRowOut], dependencies=[_AUTH])
async def list_emails(
    svc: FromDishka[MailService],
    status: EmailProcessingStatus | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EmailRowOut]:
    """Журнал: все пришедшие письма с результатом разбора."""
    return [
        email_row_to_out(e)
        for e in await svc.list_emails(status=status, search=search, limit=limit)
    ]


@router.get(
    "/emails/{email_id}/events", response_model=list[MailEventOut], dependencies=[_AUTH]
)
async def email_events(email_id: int, svc: FromDishka[MailService]) -> list[MailEventOut]:
    return [mail_event_to_out(e) for e in await svc.email_events(email_id)]


@router.get("/emails/{email_id}", response_model=EmailDetailOut, dependencies=[_AUTH])
async def email_detail(email_id: int, svc: FromDishka[MailService]) -> EmailDetailOut:
    return email_detail_to_out(await svc.get_email(email_id))


@router.post("/emails/{email_id}/resolve", status_code=204, dependencies=[_AUTH])
async def resolve_email(
    email_id: int, payload: EmailResolveIn, svc: FromDishka[MailService]
) -> None:
    await svc.resolve_email(
        email_id,
        order_id=payload.order_id,
        event_type=EmailEventType(payload.event_type) if payload.event_type else None,
        tracking_numbers=payload.tracking_numbers,
        carrier=payload.carrier,
    )


@router.post("/emails/{email_id}/retry", status_code=204, dependencies=[_AUTH])
async def retry_email(email_id: int, svc: FromDishka[MailService], request: Request) -> None:
    await svc.retry_email(email_id)
    request.app.state.mail_wake.set()


@router.post("/emails/{email_id}/ignore", status_code=204, dependencies=[_AUTH])
async def ignore_email(email_id: int, svc: FromDishka[MailService]) -> None:
    await svc.ignore_email(email_id)


@router.post("/poll", status_code=202, dependencies=[_AUTH])
async def poll_now(request: Request) -> dict:
    request.app.state.mail_wake.set()
    return {"status": "scheduled"}


@router.get("/health", response_model=MailHealthOut, dependencies=[_AUTH])
async def health(svc: FromDishka[MailService]) -> MailHealthOut:
    return mail_health_to_out(await svc.health())


@router.get("/oauth/url", response_model=OAuthUrlOut, dependencies=[_AUTH])
async def oauth_url(request: Request, svc: FromDishka[MailService]) -> OAuthUrlOut:
    state = request.app.state.auth_service.issue_state()
    states: set[str] = request.app.state.oauth_states
    if len(states) > 20:  # защитный потолок: забытые state не копятся вечно
        states.clear()
    states.add(state)
    return OAuthUrlOut(url=await svc.oauth_url(state))


# response_model=None: аннотация RedirectResponse — строка (future annotations),
# без явного None генерация OpenAPI-схемы падает на ForwardRef.
@router.get("/oauth/callback", response_model=None)
async def oauth_callback(
    request: Request,
    svc: FromDishka[MailService],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Сюда редиректит Google — без auth-cookie. CSRF закрыт подписанным
    ОДНОРАЗОВЫМ state; state проверяется первым, чтобы аноним не гонял
    редиректы с произвольным reason."""
    frontend = request.app.state.settings.frontend_base_url
    states: set[str] = request.app.state.oauth_states
    if (
        not state
        or state not in states
        or not request.app.state.auth_service.verify_state(state)
    ):
        return RedirectResponse(f"{frontend}/settings?gmail=error&reason=bad_state")
    states.discard(state)  # одноразовый: повтор с тем же state не пройдёт
    if error or not code:
        return RedirectResponse(f"{frontend}/settings?gmail=error&reason={quote(error or 'no_code')}")
    try:
        email = await svc.oauth_complete(code)
    except Exception as exc:  # noqa: BLE001 — пользователю нужен внятный редирект
        log.exception("Ошибка обмена OAuth-кода")
        return RedirectResponse(
            f"{frontend}/settings?gmail=error&reason={quote(str(exc)[:200])}"
        )
    request.app.state.mail_wake.set()
    return RedirectResponse(f"{frontend}/settings?gmail=connected&email={quote(email)}")
