from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from crm.application.interfaces.repositories import (
    DashboardRepository,
    OrderFilters,
    OrderRepository,
    TrackRepository,
)
from crm.domain.clock import business_today
from crm.domain.models import DashboardNumbers, OrderListRow, Track


@dataclass(frozen=True, slots=True)
class DashboardData:
    numbers: DashboardNumbers
    no_commission: list[OrderListRow]
    overdue: list[OrderListRow]
    unmatched_tracks: list[Track]


class DashboardService:
    def __init__(
        self,
        dashboard: DashboardRepository,
        orders: OrderRepository,
        tracks: TrackRepository,
    ) -> None:
        self._dashboard = dashboard
        self._orders = orders
        self._tracks = tracks

    async def data(self, today: date | None = None) -> DashboardData:
        today = today or business_today()
        month_start = today.replace(day=1)
        month_end_excl = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        numbers = await self._dashboard.numbers(
            month_start=month_start, month_end_excl=month_end_excl
        )
        return DashboardData(
            numbers=numbers,
            no_commission=await self._orders.list(OrderFilters(no_commission=True)),
            overdue=await self._orders.list(OrderFilters(overdue=True)),
            unmatched_tracks=await self._tracks.list(unmatched=True),
        )
