from __future__ import annotations

from datetime import date
from decimal import Decimal

import asyncpg

from crm.domain.models import MoneyReportOrderRow, MonthMoneyRow

# Заказ попадает в прибыль периода по дате закрытия (или возврата — с уже скорректированной
# комиссией). Календарная дата — по Москве (см. crm.domain.clock), не по UTC сервера.
_PERIOD_COND = """
o.commission_usd IS NOT NULL AND (
    (o.closed_at IS NOT NULL
        AND (o.closed_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN $1 AND $2)
    OR (o.refunded_at IS NOT NULL
        AND (o.refunded_at AT TIME ZONE 'Europe/Moscow')::date BETWEEN $1 AND $2)
)
"""


class PgReportRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def totals(self, date_from: date, date_to: date) -> tuple[Decimal, Decimal]:
        commissions = await self._conn.fetchval(
            f"SELECT COALESCE(SUM(o.commission_usd), 0) FROM orders o WHERE {_PERIOD_COND}",
            date_from,
            date_to,
        )
        flights = await self._conn.fetchval(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM flights "
            "WHERE departed_on BETWEEN $1 AND $2",
            date_from,
            date_to,
        )
        return commissions or Decimal("0"), flights or Decimal("0")

    async def money_orders(self, date_from: date, date_to: date) -> list[MoneyReportOrderRow]:
        rows = await self._conn.fetch(
            f"""
            SELECT o.id, c.name AS client_name, o.store, o.items, o.commission_usd, o.closed_at
            FROM orders o JOIN clients c ON c.id = o.client_id
            WHERE {_PERIOD_COND}
            ORDER BY COALESCE(o.closed_at, o.refunded_at) DESC
            """,
            date_from,
            date_to,
        )
        return [
            MoneyReportOrderRow(
                id=r["id"],
                client_name=r["client_name"],
                store=r["store"],
                items=r["items"],
                commission_usd=r["commission_usd"],
                closed_at=r["closed_at"],
            )
            for r in rows
        ]

    async def months(self, date_from: date, date_to: date) -> list[MonthMoneyRow]:
        commission_rows = await self._conn.fetch(
            f"""
            SELECT to_char(
                       date_trunc(
                           'month',
                           COALESCE(o.closed_at, o.refunded_at) AT TIME ZONE 'Europe/Moscow'
                       ),
                       'YYYY-MM'
                   ) AS month,
                   SUM(o.commission_usd) AS total
            FROM orders o WHERE {_PERIOD_COND}
            GROUP BY 1
            """,
            date_from,
            date_to,
        )
        flight_rows = await self._conn.fetch(
            """
            SELECT to_char(date_trunc('month', departed_on), 'YYYY-MM') AS month,
                   SUM(cost_usd) AS total
            FROM flights WHERE departed_on BETWEEN $1 AND $2
            GROUP BY 1
            """,
            date_from,
            date_to,
        )
        months: dict[str, dict[str, Decimal]] = {}
        for r in commission_rows:
            months.setdefault(r["month"], {})["commissions"] = r["total"] or Decimal("0")
        for r in flight_rows:
            months.setdefault(r["month"], {})["flights"] = r["total"] or Decimal("0")
        return [
            MonthMoneyRow(
                month=month,
                commissions_usd=data.get("commissions", Decimal("0")),
                flights_cost_usd=data.get("flights", Decimal("0")),
            )
            for month, data in sorted(months.items())
        ]
