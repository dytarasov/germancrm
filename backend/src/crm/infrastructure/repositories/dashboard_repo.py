from __future__ import annotations

from datetime import date
from decimal import Decimal

import asyncpg

from crm.domain import rules
from crm.domain.models import DashboardNumbers

_ACTIVE = [s.value for s in rules.ACTIVE_STATUSES]
# Закрытый заказ считается оплаченным, отменённый и возвращённый — снятыми с клиента.
# Условие по текущему статусу: переоткрытый заказ сам возвращается в долг.
_EXCLUDED_FROM_DEBT = ["closed", "cancelled", "refunded"]

_SQL = """
SELECT
    (SELECT COUNT(*) FROM orders WHERE status = ANY($3::text[])) AS in_progress,
    (SELECT COALESCE(SUM(o.purchase_price_usd + o.commission_usd - COALESCE(p.paid, 0)), 0)
       FROM orders o
       LEFT JOIN LATERAL (SELECT SUM(amount_usd) AS paid FROM payments WHERE order_id = o.id) p ON TRUE
       WHERE o.status <> ALL($4::text[]) AND o.commission_usd IS NOT NULL) AS debt,
    (SELECT COALESCE(SUM(commission_usd), 0) FROM orders
       WHERE commission_usd IS NOT NULL AND (
           ((closed_at AT TIME ZONE 'Europe/Moscow')::date >= $1::date
               AND (closed_at AT TIME ZONE 'Europe/Moscow')::date < $2::date)
           OR ((refunded_at AT TIME ZONE 'Europe/Moscow')::date >= $1::date
               AND (refunded_at AT TIME ZONE 'Europe/Moscow')::date < $2::date)))
       AS month_commissions,
    (SELECT COALESCE(SUM(cost_usd), 0) FROM flights
       WHERE departed_on >= $1::date AND departed_on < $2::date) AS month_flights
"""


class PgDashboardRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def numbers(self, *, month_start: date, month_end_excl: date) -> DashboardNumbers:
        row = await self._conn.fetchrow(
            _SQL, month_start, month_end_excl, _ACTIVE, _EXCLUDED_FROM_DEBT
        )
        assert row is not None
        return DashboardNumbers(
            orders_in_progress=row["in_progress"],
            clients_debt_usd=row["debt"] or Decimal("0"),
            month_commissions_usd=row["month_commissions"] or Decimal("0"),
            month_flights_cost_usd=row["month_flights"] or Decimal("0"),
        )
