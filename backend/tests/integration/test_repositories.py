from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import asyncpg
import pytest

from crm.application.interfaces.repositories import OrderFilters
from crm.domain.clock import business_today
from crm.domain.enums import EmailProcessingStatus, OrderStatus
from crm.domain.models import EmailMessage
from crm.infrastructure.repositories.client_repo import PgClientRepository
from crm.infrastructure.repositories.dashboard_repo import PgDashboardRepository
from crm.infrastructure.repositories.email_repo import PgEmailRepository
from crm.infrastructure.repositories.flight_repo import PgFlightRepository
from crm.infrastructure.repositories.order_repo import PgOrderRepository
from crm.infrastructure.repositories.payment_repo import PgPaymentRepository
from crm.infrastructure.repositories.report_repo import PgReportRepository
from crm.infrastructure.repositories.track_repo import PgTrackRepository

# Даты в тестах — по бизнес-календарю (Москва), как и в SQL репозиториев.
TODAY = business_today()


async def make_client_and_order(conn, **order_overrides):
    clients = PgClientRepository(conn)
    orders = PgOrderRepository(conn)
    client = await clients.add(name="Иванов", contacts=None, telegram_url=None, note=None)
    fields = {
        "client_id": client.id,
        "store": "Amazon",
        "items": "iPhone 17 Pro",
        "purchase_price_usd": Decimal("1000.00"),
    }
    fields.update(order_overrides)
    order = await orders.add(fields)
    return client, order


async def test_commission_null_vs_zero(pool):
    async with pool.acquire() as conn:
        orders = PgOrderRepository(conn)
        _, order = await make_client_and_order(conn)
        assert order.commission_usd is None

        await orders.update_fields(order.id, {"commission_usd": Decimal("0")})
        got = await orders.get(order.id)
        assert got.commission_usd == Decimal("0")

        await orders.update_fields(order.id, {"commission_usd": None})
        got = await orders.get(order.id)
        assert got.commission_usd is None  # явный NULL, а не 0


async def test_db_check_blocks_close_without_commission(pool):
    async with pool.acquire() as conn:
        _, order = await make_client_and_order(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE orders SET status = 'closed', closed_at = now() WHERE id = $1",
                order.id,
            )


async def test_order_filters(pool):
    async with pool.acquire() as conn:
        orders = PgOrderRepository(conn)
        client, o1 = await make_client_and_order(
            conn, promised_date=TODAY - timedelta(days=2)
        )
        o2 = await orders.add(
            {
                "client_id": client.id,
                "store": "eBay",
                "items": "Кроссовки Nike",
                "purchase_price_usd": Decimal("200.00"),
                "commission_usd": Decimal("40.00"),
                "status": OrderStatus.CLOSED,
                "closed_at": __import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
            }
        )
        active = await orders.list(OrderFilters(active=True))
        assert [r.order.id for r in active] == [o1.id]

        overdue = await orders.list(OrderFilters(overdue=True))
        assert [r.order.id for r in overdue] == [o1.id]

        no_comm = await orders.list(OrderFilters(no_commission=True))
        assert [r.order.id for r in no_comm] == [o1.id]

        closed = await orders.list(OrderFilters(active=False))
        assert [r.order.id for r in closed] == [o2.id]

        by_search = await orders.list(OrderFilters(search="nike"))
        assert [r.order.id for r in by_search] == [o2.id]


async def test_track_unique_and_unmatched(pool):
    async with pool.acquire() as conn:
        tracks = PgTrackRepository(conn)
        from crm.domain.exceptions import DuplicateError

        t = await tracks.add(
            tracking_number="1Z999AA10123456784",
            carrier="ups",
            order_id=None,
            source="email",
            email_log_id=None,
            match_status="open",
            candidates=[{"order_id": 1, "score": 55, "reasons": ["тест"], "order_label": "Заказ #1"}],
            note=None,
        )
        assert t.candidates[0].score == 55

        with pytest.raises(DuplicateError):
            await tracks.add(
                tracking_number="1Z999AA10123456784",
                carrier=None,
                order_id=None,
                source="manual",
                email_log_id=None,
                match_status="open",
                candidates=None,
                note=None,
            )

        open_tracks = await tracks.open_tracks()
        assert len(open_tracks) == 1


async def test_payments_sum_and_client_stats(pool):
    async with pool.acquire() as conn:
        payments = PgPaymentRepository(conn)
        clients = PgClientRepository(conn)
        orders = PgOrderRepository(conn)
        client, order = await make_client_and_order(conn)
        await orders.update_fields(order.id, {"commission_usd": Decimal("100.00")})
        await payments.add(
            order_id=order.id, paid_on=TODAY, amount_usd=Decimal("300.00"), comment=None
        )
        await payments.add(
            order_id=order.id, paid_on=TODAY, amount_usd=Decimal("200.00"), comment="частями"
        )
        assert await payments.sum_for_order(order.id) == Decimal("500.00")

        stats = await clients.stats(client.id)
        # выручка 1100, оплачено 500 -> долг 600
        assert stats.debt_usd == Decimal("600.00")
        assert stats.active_orders == 1

        items = await clients.list()
        assert items[0].debt_usd == Decimal("600.00")


async def test_debt_skips_closed_and_returns_on_reopen(pool):
    async with pool.acquire() as conn:
        clients = PgClientRepository(conn)
        orders = PgOrderRepository(conn)
        dash = PgDashboardRepository(conn)
        reports = PgReportRepository(conn)
        client, order = await make_client_and_order(conn, commission_usd=Decimal("100.00"))
        month_start = TODAY.replace(day=1)
        month_end = (month_start + timedelta(days=40)).replace(day=1)

        async def numbers():
            return await dash.numbers(month_start=month_start, month_end_excl=month_end)

        assert (await clients.stats(client.id)).debt_usd == Decimal("1100.00")
        assert (await numbers()).clients_debt_usd == Decimal("1100.00")

        # закрыт = оплачен: из долга уходит, комиссия попадает в прибыль
        await orders.update_fields(
            order.id,
            {"status": OrderStatus.CLOSED, "closed_at": __import__("datetime").datetime.now(
                __import__("datetime").UTC
            )},
        )
        stats = await clients.stats(client.id)
        assert (stats.debt_usd, stats.earned_usd) == (Decimal("0"), Decimal("100.00"))
        assert (await clients.list())[0].debt_usd == Decimal("0")
        closed = await numbers()
        assert closed.clients_debt_usd == Decimal("0")
        assert closed.month_commissions_usd == Decimal("100.00")

        # закрыли по ошибке и вернули статус — всё как до закрытия
        await orders.update_fields(
            order.id, {"status": OrderStatus.DELIVERED, "closed_at": None}
        )
        stats = await clients.stats(client.id)
        assert (stats.debt_usd, stats.earned_usd) == (Decimal("1100.00"), Decimal("0"))
        assert stats.active_orders == 1
        assert (await clients.list())[0].debt_usd == Decimal("1100.00")
        reopened = await numbers()
        assert reopened.clients_debt_usd == Decimal("1100.00")
        assert reopened.month_commissions_usd == Decimal("0")
        assert reopened.orders_in_progress == 1
        assert (await reports.totals(month_start, month_end))[0] == Decimal("0")

        # отменённый в долг не входит
        await orders.update_fields(order.id, {"status": OrderStatus.CANCELLED})
        assert (await clients.stats(client.id)).debt_usd == Decimal("0")
        assert (await numbers()).clients_debt_usd == Decimal("0")


async def test_dashboard_and_report_numbers(pool):
    async with pool.acquire() as conn:
        orders = PgOrderRepository(conn)
        flights = PgFlightRepository(conn)
        dash = PgDashboardRepository(conn)
        reports = PgReportRepository(conn)
        client, o_active = await make_client_and_order(conn)

        import datetime as dt

        now = dt.datetime.now(dt.UTC)
        await orders.add(
            {
                "client_id": client.id,
                "store": "eBay",
                "items": "Перчатки",
                "purchase_price_usd": Decimal("100.00"),
                "commission_usd": Decimal("50.00"),
                "status": OrderStatus.CLOSED,
                "closed_at": now,
            }
        )
        await flights.add(
            departed_on=TODAY, cost_usd=Decimal("30.00"), description="Рейс август"
        )

        month_start = TODAY.replace(day=1)
        month_end = (month_start + timedelta(days=40)).replace(day=1)
        numbers = await dash.numbers(month_start=month_start, month_end_excl=month_end)
        assert numbers.orders_in_progress == 1
        assert numbers.month_commissions_usd == Decimal("50.00")
        assert numbers.month_flights_cost_usd == Decimal("30.00")
        assert numbers.month_profit_usd == Decimal("20.00")

        commissions, flights_cost = await reports.totals(month_start, month_end)
        assert (commissions, flights_cost) == (Decimal("50.00"), Decimal("30.00"))
        months = await reports.months(month_start, month_end)
        assert len(months) == 1
        assert months[0].profit_usd == Decimal("20.00")


async def test_email_log_idempotent_insert(pool):
    async with pool.acquire() as conn:
        emails = PgEmailRepository(conn)
        msg = EmailMessage(
            gmail_message_id="gm-123",
            gmail_thread_id="th-1",
            message_id_hdr="<abc@amazon.com>",
            from_addr="ship-confirm@amazon.com",
            from_domain="amazon.com",
            subject="Shipped",
            sent_at=None,
            snippet=None,
            body_text="Track 1Z999AA10123456784",
        )
        first = await emails.insert_ingested(msg, EmailProcessingStatus.NEW)
        second = await emails.insert_ingested(msg, EmailProcessingStatus.NEW)
        assert first is not None
        assert second is None  # дедуп по gmail_message_id

        counts = await emails.status_counts()
        assert counts.get("new") == 1

        # журнал: фильтр по статусу и поиск
        all_rows = await emails.list_all()
        assert len(all_rows) == 1
        assert await emails.list_all(status=EmailProcessingStatus.PROCESSED) == []
        assert len(await emails.list_all(search="amazon")) == 1
        assert await emails.list_all(search="ebay") == []
