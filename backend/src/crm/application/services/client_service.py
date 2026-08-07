from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crm.application.interfaces.repositories import (
    ClientRepository,
    OrderFilters,
    OrderRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.domain.exceptions import NotFoundError
from crm.domain.models import Client, ClientListItem, ClientStats, OrderListRow


@dataclass(frozen=True, slots=True)
class ClientDetail:
    client: Client
    orders: list[OrderListRow]
    stats: ClientStats


class ClientService:
    def __init__(self, clients: ClientRepository, orders: OrderRepository, uow: UnitOfWork) -> None:
        self._clients = clients
        self._orders = orders
        self._uow = uow

    async def create(
        self,
        *,
        name: str,
        contacts: str | None = None,
        telegram_url: str | None = None,
        note: str | None = None,
    ) -> Client:
        async with self._uow:
            return await self._clients.add(
                name=name, contacts=contacts, telegram_url=telegram_url, note=note
            )

    async def list(self, search: str | None = None) -> list[ClientListItem]:
        return await self._clients.list(search)

    async def get_detail(self, client_id: int) -> ClientDetail:
        client = await self._clients.get(client_id)
        if client is None:
            raise NotFoundError.entity("Клиент", client_id)
        orders = await self._orders.list(OrderFilters(client_id=client_id))
        stats = await self._clients.stats(client_id)
        return ClientDetail(client=client, orders=orders, stats=stats)

    async def update(self, client_id: int, fields: dict[str, Any]) -> Client:
        async with self._uow:
            client = await self._clients.update(client_id, fields)
        if client is None:
            raise NotFoundError.entity("Клиент", client_id)
        return client

    async def delete(self, client_id: int) -> None:
        async with self._uow:
            if await self._clients.get(client_id) is None:
                raise NotFoundError.entity("Клиент", client_id)
            await self._clients.delete(client_id)
