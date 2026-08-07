from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from crm.application.interfaces.repositories import FlightRepository, ReportRepository
from crm.domain.exceptions import DomainValidationError
from crm.domain.models import Flight, MoneyReportOrderRow, MonthMoneyRow


@dataclass(frozen=True, slots=True)
class MoneyReport:
    date_from: date
    date_to: date
    commissions_usd: Decimal
    flights_cost_usd: Decimal
    orders: list[MoneyReportOrderRow]
    flights: list[Flight]
    months: list[MonthMoneyRow]

    @property
    def profit_usd(self) -> Decimal:
        return self.commissions_usd - self.flights_cost_usd


class ReportService:
    def __init__(self, reports: ReportRepository, flights: FlightRepository) -> None:
        self._reports = reports
        self._flights = flights

    async def money(self, date_from: date, date_to: date) -> MoneyReport:
        if date_from > date_to:
            raise DomainValidationError("Начало периода позже конца")
        commissions, flights_cost = await self._reports.totals(date_from, date_to)
        return MoneyReport(
            date_from=date_from,
            date_to=date_to,
            commissions_usd=commissions,
            flights_cost_usd=flights_cost,
            orders=await self._reports.money_orders(date_from, date_to),
            flights=await self._flights.list(date_from=date_from, date_to=date_to),
            months=await self._reports.months(date_from, date_to),
        )
