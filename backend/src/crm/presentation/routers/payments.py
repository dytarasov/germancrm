from __future__ import annotations

from datetime import date
from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, Query

from crm.application.services.payment_service import PaymentService
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import payment_to_out
from crm.presentation.schemas.payments import PaymentOut, PaymentUpdate

router = APIRouter(
    prefix="/api/payments",
    tags=["payments"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[PaymentOut])
async def list_payments(
    svc: FromDishka[PaymentService],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    client_id: int | None = None,
) -> list[PaymentOut]:
    payments = await svc.list(date_from=date_from, date_to=date_to, client_id=client_id)
    return [payment_to_out(p) for p in payments]


@router.patch("/{payment_id}", response_model=PaymentOut)
async def update_payment(
    payment_id: int, payload: PaymentUpdate, svc: FromDishka[PaymentService]
) -> PaymentOut:
    payment = await svc.update(payment_id, payload.model_dump(exclude_unset=True))
    return payment_to_out(payment)


@router.delete("/{payment_id}", status_code=204)
async def delete_payment(payment_id: int, svc: FromDishka[PaymentService]) -> None:
    await svc.delete(payment_id)
