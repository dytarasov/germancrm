from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.interfaces.repositories import OrderFilters
from crm.application.services.client_service import ClientService
from crm.application.services.order_service import OrderService
from crm.application.services.track_service import TrackService
from crm.domain.clock import business_today
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import (
    client_item_to_out,
    order_row_to_out,
    track_to_out,
)
from crm.presentation.schemas.search import SearchOut

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=SearchOut)
async def search(
    q: str,
    clients: FromDishka[ClientService],
    orders: FromDishka[OrderService],
    tracks: FromDishka[TrackService],
) -> SearchOut:
    q = q.strip()
    if not q:
        return SearchOut(clients=[], orders=[], tracks=[])
    today = business_today()
    return SearchOut(
        clients=[client_item_to_out(c) for c in (await clients.list(q))[:10]],
        orders=[
            order_row_to_out(r, today)
            for r in (await orders.list(OrderFilters(search=q)))[:15]
        ],
        tracks=[track_to_out(t) for t in (await tracks.list(search=q))[:10]],
    )
