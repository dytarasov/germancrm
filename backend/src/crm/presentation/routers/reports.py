from __future__ import annotations

from datetime import date
from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, Query

from crm.application.services.report_service import ReportService
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import flight_to_out
from crm.presentation.schemas.reports import (
    MoneyOrderRowOut,
    MoneyReportOut,
    MonthRowOut,
)

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("/money", response_model=MoneyReportOut, response_model_by_alias=True)
async def money_report(
    svc: FromDishka[ReportService],
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> MoneyReportOut:
    report = await svc.money(date_from, date_to)
    return MoneyReportOut(
        date_from=report.date_from,
        date_to=report.date_to,
        commissions_usd=report.commissions_usd,
        flights_cost_usd=report.flights_cost_usd,
        profit_usd=report.profit_usd,
        orders=[
            MoneyOrderRowOut(
                id=o.id,
                client_name=o.client_name,
                store=o.store,
                items=o.items,
                commission_usd=o.commission_usd,
                closed_at=o.closed_at,
            )
            for o in report.orders
        ],
        flights=[flight_to_out(f) for f in report.flights],
        months=[
            MonthRowOut(
                month=m.month,
                commissions_usd=m.commissions_usd,
                flights_cost_usd=m.flights_cost_usd,
                profit_usd=m.profit_usd,
            )
            for m in report.months
        ],
    )
