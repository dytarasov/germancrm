from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from crm.application.interfaces.repositories import (
    FlightRepository,
    OrderFilters,
    OrderRepository,
)
from crm.application.interfaces.uow import UnitOfWork
from crm.domain.exceptions import NotFoundError
from crm.domain.models import Flight, OrderListRow


@dataclass(frozen=True, slots=True)
class FlightDetail:
    flight: Flight
    orders: list[OrderListRow]


class FlightService:
    def __init__(self, flights: FlightRepository, orders: OrderRepository, uow: UnitOfWork) -> None:
        self._flights = flights
        self._orders = orders
        self._uow = uow

    async def create(
        self, *, departed_on: date, cost_usd: Decimal, description: str | None = None
    ) -> Flight:
        async with self._uow:
            return await self._flights.add(
                departed_on=departed_on, cost_usd=cost_usd, description=description
            )

    async def list(self) -> list[Flight]:
        return await self._flights.list()

    async def get_detail(self, flight_id: int) -> FlightDetail:
        flight = await self._flights.get(flight_id)
        if flight is None:
            raise NotFoundError.entity("Рейс", flight_id)
        orders = await self._orders.list(OrderFilters(flight_id=flight_id))
        return FlightDetail(flight=flight, orders=orders)

    async def update(self, flight_id: int, fields: dict[str, Any]) -> Flight:
        async with self._uow:
            flight = await self._flights.update(flight_id, fields)
        if flight is None:
            raise NotFoundError.entity("Рейс", flight_id)
        return flight

    async def delete(self, flight_id: int) -> None:
        async with self._uow:
            if await self._flights.get(flight_id) is None:
                raise NotFoundError.entity("Рейс", flight_id)
            await self._flights.delete(flight_id)
