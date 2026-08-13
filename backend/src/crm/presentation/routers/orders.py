from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.interfaces.repositories import OrderFilters
from crm.application.services.order_service import OrderService
from crm.application.services.payment_service import PaymentService
from crm.application.services.track_service import TrackService
from crm.domain.clock import business_today
from crm.domain.enums import OrderStatus
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import (
    order_detail_to_out,
    order_item_to_out,
    order_row_to_out,
    payment_to_out,
    status_change_to_out,
    suborder_to_out,
    track_to_out,
)
from crm.presentation.schemas.orders import (
    OrderCreate,
    OrderDetailOut,
    OrderItemCreate,
    OrderItemOut,
    OrderItemUpdate,
    OrderListItemOut,
    OrderUpdate,
    RefundIn,
    StatusChangeIn,
    StatusChangeOut,
    SuborderIn,
    SuborderOut,
    SuborderStatusIn,
    SuborderUpdate,
)
from crm.presentation.schemas.payments import PaymentCreate, PaymentOut
from crm.presentation.schemas.tracks import OrderTrackCreate, TrackOut

router = APIRouter(
    prefix="/api/orders",
    tags=["orders"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=OrderDetailOut, status_code=201)
async def create_order(payload: OrderCreate, svc: FromDishka[OrderService]) -> OrderDetailOut:
    fields = payload.model_dump()
    if fields.get("purchased_on") is None:
        fields.pop("purchased_on", None)
    return order_detail_to_out(await svc.create(fields), business_today())


@router.get("", response_model=list[OrderListItemOut])
async def list_orders(
    svc: FromDishka[OrderService],
    status: OrderStatus | None = None,
    client_id: int | None = None,
    active: bool | None = None,
    overdue: bool = False,
    no_commission: bool = False,
    search: str | None = None,
    flight_id: int | None = None,
) -> list[OrderListItemOut]:
    rows = await svc.list(
        OrderFilters(
            status=status,
            client_id=client_id,
            active=active,
            overdue=overdue,
            no_commission=no_commission,
            search=search,
            flight_id=flight_id,
        )
    )
    today = business_today()
    return [order_row_to_out(r, today) for r in rows]


@router.get("/{order_id}", response_model=OrderDetailOut)
async def get_order(order_id: int, svc: FromDishka[OrderService]) -> OrderDetailOut:
    return order_detail_to_out(await svc.get_detail(order_id), business_today())


@router.patch("/{order_id}", response_model=OrderDetailOut)
async def update_order(
    order_id: int, payload: OrderUpdate, svc: FromDishka[OrderService]
) -> OrderDetailOut:
    fields = payload.model_dump(exclude_unset=True)
    return order_detail_to_out(await svc.update(order_id, fields), business_today())


@router.delete("/{order_id}", status_code=204)
async def delete_order(order_id: int, svc: FromDishka[OrderService]) -> None:
    await svc.delete(order_id)


@router.post("/{order_id}/status", response_model=OrderDetailOut)
async def set_status(
    order_id: int, payload: StatusChangeIn, svc: FromDishka[OrderService]
) -> OrderDetailOut:
    detail = await svc.set_status(order_id, payload.status, comment=payload.comment)
    return order_detail_to_out(detail, business_today())


@router.post("/{order_id}/close", response_model=OrderDetailOut)
async def close_order(order_id: int, svc: FromDishka[OrderService]) -> OrderDetailOut:
    return order_detail_to_out(await svc.close(order_id), business_today())


@router.post("/{order_id}/cancel", response_model=OrderDetailOut)
async def cancel_order(order_id: int, svc: FromDishka[OrderService]) -> OrderDetailOut:
    return order_detail_to_out(await svc.cancel(order_id), business_today())


@router.post("/{order_id}/refund", response_model=OrderDetailOut)
async def refund_order(
    order_id: int, payload: RefundIn, svc: FromDishka[OrderService]
) -> OrderDetailOut:
    detail = await svc.refund(
        order_id,
        refunded_amount_usd=payload.refunded_amount_usd,
        commission_usd=payload.commission_usd,
        commission_provided="commission_usd" in payload.model_fields_set,
    )
    return order_detail_to_out(detail, business_today())


@router.post("/{order_id}/copy", response_model=OrderDetailOut, status_code=201)
async def copy_order(order_id: int, svc: FromDishka[OrderService]) -> OrderDetailOut:
    return order_detail_to_out(await svc.copy(order_id), business_today())


@router.get("/{order_id}/status-history", response_model=list[StatusChangeOut])
async def status_history(order_id: int, svc: FromDishka[OrderService]) -> list[StatusChangeOut]:
    detail = await svc.get_detail(order_id)
    return [status_change_to_out(s) for s in detail.history]


@router.post("/{order_id}/suborders", response_model=SuborderOut, status_code=201)
async def add_suborder(
    order_id: int, payload: SuborderIn, svc: FromDishka[OrderService]
) -> SuborderOut:
    sub = await svc.add_suborder(
        order_id,
        store_order_number=payload.store_order_number,
        amount_usd=payload.amount_usd,
    )
    return suborder_to_out(sub)


@router.patch("/{order_id}/suborders/{suborder_id}", response_model=SuborderOut)
async def update_suborder(
    order_id: int, suborder_id: int, payload: SuborderUpdate, svc: FromDishka[OrderService]
) -> SuborderOut:
    sub = await svc.update_suborder(
        order_id, suborder_id, payload.model_dump(exclude_unset=True)
    )
    return suborder_to_out(sub)


@router.delete("/{order_id}/suborders/{suborder_id}", status_code=204)
async def delete_suborder(
    order_id: int, suborder_id: int, svc: FromDishka[OrderService]
) -> None:
    await svc.delete_suborder(order_id, suborder_id)


@router.post("/{order_id}/suborders/{suborder_id}/status", response_model=OrderDetailOut)
async def set_suborder_status(
    order_id: int, suborder_id: int, payload: SuborderStatusIn, svc: FromDishka[OrderService]
) -> OrderDetailOut:
    detail = await svc.set_suborder_status(
        order_id, suborder_id, payload.status, comment=payload.comment
    )
    return order_detail_to_out(detail, business_today())


@router.post("/{order_id}/tracks", response_model=TrackOut, status_code=201)
async def add_track(
    order_id: int, payload: OrderTrackCreate, svc: FromDishka[TrackService]
) -> TrackOut:
    track = await svc.create(
        tracking_number=payload.tracking_number,
        carrier=payload.carrier,
        order_id=order_id,
        note=payload.note,
    )
    return track_to_out(track)


@router.post("/{order_id}/items", response_model=OrderItemOut, status_code=201)
async def add_order_item(
    order_id: int, payload: OrderItemCreate, svc: FromDishka[OrderService]
) -> OrderItemOut:
    item = await svc.add_item(
        order_id,
        title=payload.title,
        url=payload.url,
        quantity=payload.quantity,
        note=payload.note,
    )
    return order_item_to_out(item)


@router.patch("/{order_id}/items/{item_id}", response_model=OrderItemOut)
async def update_order_item(
    order_id: int, item_id: int, payload: OrderItemUpdate, svc: FromDishka[OrderService]
) -> OrderItemOut:
    item = await svc.update_item(order_id, item_id, payload.model_dump(exclude_unset=True))
    return order_item_to_out(item)


@router.delete("/{order_id}/items/{item_id}", status_code=204)
async def delete_order_item(
    order_id: int, item_id: int, svc: FromDishka[OrderService]
) -> None:
    await svc.delete_item(order_id, item_id)


@router.get("/{order_id}/payments", response_model=list[PaymentOut])
async def order_payments(order_id: int, svc: FromDishka[PaymentService]) -> list[PaymentOut]:
    return [payment_to_out(p) for p in await svc.list_for_order(order_id)]


@router.post("/{order_id}/payments", response_model=PaymentOut, status_code=201)
async def add_payment(
    order_id: int, payload: PaymentCreate, svc: FromDishka[PaymentService]
) -> PaymentOut:
    payment = await svc.add_to_order(
        order_id,
        amount_usd=payload.amount_usd,
        paid_on=payload.paid_on,
        comment=payload.comment,
    )
    return payment_to_out(payment)
