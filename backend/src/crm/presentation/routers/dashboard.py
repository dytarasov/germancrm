from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.services.dashboard_service import DashboardService
from crm.application.services.mail_service import MailService
from crm.domain.clock import business_today
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import (
    mail_health_to_out,
    order_row_to_out,
    track_to_out,
)
from crm.presentation.schemas.dashboard import AttentionOut, DashboardOut

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=DashboardOut)
async def dashboard(
    svc: FromDishka[DashboardService], mail: FromDishka[MailService]
) -> DashboardOut:
    today = business_today()
    data = await svc.data(today)
    health = await mail.health()
    n = data.numbers
    return DashboardOut(
        orders_in_progress=n.orders_in_progress,
        clients_debt_usd=n.clients_debt_usd,
        month_profit_usd=n.month_profit_usd,
        month_commissions_usd=n.month_commissions_usd,
        month_flights_cost_usd=n.month_flights_cost_usd,
        attention=AttentionOut(
            no_commission=[order_row_to_out(r, today) for r in data.no_commission],
            overdue=[order_row_to_out(r, today) for r in data.overdue],
            unmatched_tracks=[track_to_out(t) for t in data.unmatched_tracks],
        ),
        mail=mail_health_to_out(health),
    )
