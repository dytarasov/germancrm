from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends

from crm.application.services.client_service import ClientService
from crm.domain.clock import business_today
from crm.presentation.auth import require_auth
from crm.presentation.mappers.api_mappers import (
    client_detail_to_out,
    client_item_to_out,
    client_to_out,
)
from crm.presentation.schemas.clients import (
    ClientCreate,
    ClientDetailOut,
    ClientListItemOut,
    ClientOut,
    ClientUpdate,
)

router = APIRouter(
    prefix="/api/clients",
    tags=["clients"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(payload: ClientCreate, svc: FromDishka[ClientService]) -> ClientOut:
    client = await svc.create(**payload.model_dump())
    return client_to_out(client)


@router.get("", response_model=list[ClientListItemOut])
async def list_clients(
    svc: FromDishka[ClientService], search: str | None = None
) -> list[ClientListItemOut]:
    return [client_item_to_out(i) for i in await svc.list(search)]


@router.get("/{client_id}", response_model=ClientDetailOut)
async def get_client(client_id: int, svc: FromDishka[ClientService]) -> ClientDetailOut:
    return client_detail_to_out(await svc.get_detail(client_id), business_today())


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int, payload: ClientUpdate, svc: FromDishka[ClientService]
) -> ClientOut:
    client = await svc.update(client_id, payload.model_dump(exclude_unset=True))
    return client_to_out(client)


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: int, svc: FromDishka[ClientService]) -> None:
    await svc.delete(client_id)
