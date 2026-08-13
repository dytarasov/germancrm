from decimal import Decimal

import pytest

from crm.application.services.order_service import OrderService
from crm.domain.enums import OrderStatus, StatusSource
from crm.domain.exceptions import (
    CommissionRequiredError,
    DomainValidationError,
    InvalidStatusTransitionError,
)
from tests.unit.fakes import (
    FakeOrderItemRepository,
    FakeOrderRepository,
    FakePaymentRepository,
    FakeSettingsRepository,
    FakeStatusHistoryRepository,
    FakeSuborderRepository,
    FakeTrackRepository,
    FakeUnitOfWork,
    make_order,
)


@pytest.fixture
def suborders() -> FakeSuborderRepository:
    return FakeSuborderRepository()


@pytest.fixture
def orders(suborders) -> FakeOrderRepository:
    return FakeOrderRepository(suborders)


@pytest.fixture
def history() -> FakeStatusHistoryRepository:
    return FakeStatusHistoryRepository()


@pytest.fixture
def items() -> FakeOrderItemRepository:
    return FakeOrderItemRepository()


@pytest.fixture
def service(orders, history, items, suborders) -> OrderService:
    return OrderService(
        orders,
        items,
        FakeTrackRepository(),
        FakePaymentRepository(),
        history,
        FakeSettingsRepository(),
        suborders,
        FakeUnitOfWork(),
    )


class TestClose:
    async def test_close_without_commission_blocked(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=None, status=OrderStatus.DELIVERED))
        with pytest.raises(CommissionRequiredError):
            await service.close(1)
        assert orders.storage[1].status == OrderStatus.DELIVERED

    async def test_close_with_zero_commission_ok(self, service, orders, history):
        orders.seed(make_order(id=1, commission_usd=Decimal("0"), status=OrderStatus.DELIVERED))
        detail = await service.close(1)
        assert detail.order.status == OrderStatus.CLOSED
        assert detail.order.closed_at is not None
        assert history.entries[-1].new_status == OrderStatus.CLOSED
        assert history.entries[-1].source == StatusSource.MANUAL

    async def test_reopen_clears_closed_at(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=Decimal("50"), status=OrderStatus.DELIVERED))
        await service.close(1)
        detail = await service.set_status(1, OrderStatus.DELIVERED)
        assert detail.order.status == OrderStatus.DELIVERED
        assert detail.order.closed_at is None


class TestManualStatus:
    async def test_backward_move_allowed_manually(self, service, orders):
        orders.seed(make_order(id=1, status=OrderStatus.AT_WAREHOUSE))
        detail = await service.set_status(1, OrderStatus.SHIPPED)
        assert detail.order.status == OrderStatus.SHIPPED

    async def test_cancel_refund_not_via_set_status(self, service, orders):
        orders.seed(make_order(id=1))
        with pytest.raises(DomainValidationError):
            await service.set_status(1, OrderStatus.CANCELLED)
        with pytest.raises(DomainValidationError):
            await service.set_status(1, OrderStatus.REFUNDED)

    async def test_noop_same_status_no_history(self, service, orders, history):
        orders.seed(make_order(id=1, status=OrderStatus.SHIPPED))
        await service.set_status(1, OrderStatus.SHIPPED)
        assert history.entries == []

    async def test_cannot_erase_commission_of_closed(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=Decimal("10"), status=OrderStatus.DELIVERED))
        await service.close(1)
        with pytest.raises(DomainValidationError):
            await service.update(1, {"commission_usd": None})


class TestAutoCommission:
    """Фактический вес заполняет комиссию по тарифу — но никогда не перетирает ручную."""

    async def test_weight_fills_empty_commission_by_tariff(
        self, orders, history, items, suborders
    ):
        settings = FakeSettingsRepository({"commission.per_kg_usd": 60})
        service = OrderService(
            orders,
            items,
            FakeTrackRepository(),
            FakePaymentRepository(),
            history,
            settings,
            suborders,
            FakeUnitOfWork(),
        )
        orders.seed(make_order(id=1, commission_usd=None))
        detail = await service.update(1, {"weight_kg": Decimal("2.5")})
        assert detail.order.commission_usd == Decimal("150.00")

    async def test_default_tariff_when_setting_absent(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=None))
        detail = await service.update(1, {"weight_kg": Decimal("1.5")})
        assert detail.order.commission_usd == Decimal("75.00")

    async def test_weight_does_not_touch_manual_commission(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=Decimal("80")))
        detail = await service.update(1, {"weight_kg": Decimal("2.5")})
        assert detail.order.commission_usd == Decimal("80")

    async def test_explicit_commission_in_same_patch_wins(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=None))
        detail = await service.update(
            1, {"weight_kg": Decimal("2"), "commission_usd": Decimal("70")}
        )
        assert detail.order.commission_usd == Decimal("70")

    async def test_est_weight_never_fills_commission(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=None))
        detail = await service.update(1, {"est_weight_kg": Decimal("3")})
        assert detail.order.commission_usd is None

    async def test_clearing_weight_keeps_commission(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=Decimal("100"), weight_kg=Decimal("2")))
        detail = await service.update(1, {"weight_kg": None})
        assert detail.order.commission_usd == Decimal("100")


class TestCancelRefund:
    async def test_cancel(self, service, orders, history):
        orders.seed(make_order(id=1, status=OrderStatus.SHIPPED))
        detail = await service.cancel(1)
        assert detail.order.status == OrderStatus.CANCELLED
        assert history.entries[-1].new_status == OrderStatus.CANCELLED

    async def test_cancel_closed_forbidden(self, service, orders):
        orders.seed(
            make_order(id=1, status=OrderStatus.DELIVERED, commission_usd=Decimal("5"))
        )
        await service.close(1)
        with pytest.raises(InvalidStatusTransitionError):
            await service.cancel(1)

    async def test_refund_records_amount_and_updates_commission(self, service, orders):
        orders.seed(
            make_order(id=1, status=OrderStatus.AT_WAREHOUSE, commission_usd=Decimal("100"))
        )
        detail = await service.refund(
            1,
            refunded_amount_usd=Decimal("950"),
            commission_usd=Decimal("20"),
            commission_provided=True,
        )
        assert detail.order.status == OrderStatus.REFUNDED
        assert detail.order.refunded_amount_usd == Decimal("950")
        assert detail.order.refunded_at is not None
        assert detail.order.commission_usd == Decimal("20")

    async def test_refund_keeps_commission_if_not_provided(self, service, orders):
        orders.seed(make_order(id=1, commission_usd=Decimal("100")))
        detail = await service.refund(
            1, refunded_amount_usd=Decimal("1000"), commission_provided=False
        )
        assert detail.order.commission_usd == Decimal("100")

    async def test_refund_cancelled_forbidden(self, service, orders):
        orders.seed(make_order(id=1, status=OrderStatus.CANCELLED))
        with pytest.raises(InvalidStatusTransitionError):
            await service.refund(1, refunded_amount_usd=Decimal("10"))

    async def test_repeat_refund_fixes_amount_without_moving_period(
        self, service, orders, history
    ):
        """Повторный refund правит сумму, но НЕ переписывает refunded_at —
        иначе комиссия уехала бы в другой отчётный месяц."""
        orders.seed(make_order(id=1, commission_usd=Decimal("100")))
        first = await service.refund(1, refunded_amount_usd=Decimal("500"))
        first_at = first.order.refunded_at
        second = await service.refund(1, refunded_amount_usd=Decimal("450"))
        assert second.order.refunded_amount_usd == Decimal("450")
        assert second.order.refunded_at == first_at
        refund_entries = [e for e in history.entries if e.new_status == OrderStatus.REFUNDED]
        assert len(refund_entries) == 1


class TestCopy:
    async def test_copy_resets_operational_fields(self, service, orders):
        orders.seed(
            make_order(
                id=1,
                status=OrderStatus.CANCELLED,
                commission_usd=Decimal("55"),
                weight_kg=Decimal("2.4"),
                est_weight_kg=Decimal("2.0"),
            ),
            order_number="113-111",
        )
        detail = await service.copy(1)
        copy = detail.order
        assert copy.id != 1
        assert copy.copied_from == 1
        assert copy.status == OrderStatus.PURCHASED
        # перезаказ получает один пустой подзаказ — номера магазина будут новые
        assert [s.store_order_number for s in detail.suborders] == [None]
        assert copy.commission_usd == Decimal("55")
        assert copy.weight_kg is None  # факт принадлежит старой посылке
        assert copy.est_weight_kg == Decimal("2.0")
        assert detail.tracks == []
        assert detail.payments == []


class TestDelete:
    async def test_delete_releases_tracks_to_open_queue(
        self, orders, history, items, suborders
    ):
        tracks = FakeTrackRepository()
        service = OrderService(
            orders,
            items,
            tracks,
            FakePaymentRepository(),
            history,
            FakeSettingsRepository(),
            suborders,
            FakeUnitOfWork(),
        )
        orders.seed(make_order(id=1))
        await tracks.add(
            tracking_number="1Z999AA10123456784",
            carrier="ups",
            order_id=1,
            source="email",
            email_log_id=None,
            match_status="linked",
            candidates=None,
            note=None,
        )
        await service.delete(1)
        track = await tracks.get_by_number("1Z999AA10123456784")
        assert track.order_id is None
        assert str(track.match_status) == "open"  # вернулся в очередь, не «осиротел»

    async def test_delete_keeps_dismissed_tracks_dismissed(
        self, orders, history, items, suborders
    ):
        tracks = FakeTrackRepository()
        service = OrderService(
            orders,
            items,
            tracks,
            FakePaymentRepository(),
            history,
            FakeSettingsRepository(),
            suborders,
            FakeUnitOfWork(),
        )
        orders.seed(make_order(id=1))
        await tracks.add(
            tracking_number="9400111899223197428490",
            carrier="usps",
            order_id=1,
            source="email",
            email_log_id=None,
            match_status="dismissed",
            candidates=None,
            note=None,
        )
        await service.delete(1)
        track = await tracks.get_by_number("9400111899223197428490")
        assert track.order_id is None
        assert str(track.match_status) == "dismissed"  # решение человека не отменяем


class TestOrderItems:
    async def test_create_with_links_makes_positions(self, service):
        detail = await service.create(
            {
                "client_id": 1,
                "store": "Amazon",
                "items": "Составной заказ",
                "purchase_price_usd": Decimal("100"),
                "links": [
                    " https://amazon.com/dp/B0ABC ",
                    "https://amazon.com/dp/B0DEF",
                    "",
                ],
            }
        )
        urls = [i.url for i in detail.order_items]
        assert urls == ["https://amazon.com/dp/B0ABC", "https://amazon.com/dp/B0DEF"]

    async def test_copy_copies_items(self, service, orders, items):
        orders.seed(make_order(id=1))
        await service.add_item(1, title="iPhone 17 Pro", url="https://a.co/x", quantity=2)
        await service.add_item(1, url="https://a.co/y")
        detail = await service.copy(1)
        copied = detail.order_items
        assert len(copied) == 2
        assert copied[0].title == "iPhone 17 Pro"
        assert copied[0].quantity == 2
        assert all(i.order_id == detail.order.id for i in copied)

    async def test_item_requires_title_or_url(self, service, orders):
        orders.seed(make_order(id=1))
        with pytest.raises(DomainValidationError):
            await service.add_item(1, title="  ", url="")
        item = await service.add_item(1, title="Кабель")
        with pytest.raises(DomainValidationError):
            await service.update_item(1, item.id, {"title": None})

    async def test_item_belongs_to_order(self, service, orders):
        orders.seed(make_order(id=1))
        orders.seed(make_order(id=2))
        item = await service.add_item(1, title="Товар")
        from crm.domain.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await service.delete_item(2, item.id)


class TestAutoAdvance:
    async def test_advance_forward(self, service, orders, history):
        orders.seed(make_order(id=1, status=OrderStatus.PURCHASED))
        outcome = await service.advance_status_auto(1, OrderStatus.SHIPPED, email_log_id=7)
        assert outcome == "advanced"
        assert orders.storage[1].status == OrderStatus.SHIPPED
        assert history.entries[-1].source == StatusSource.AUTO
        assert history.entries[-1].email_log_id == 7

    async def test_stale_email_ignored(self, service, orders, history):
        orders.seed(make_order(id=1, status=OrderStatus.IN_FLIGHT))
        assert await service.advance_status_auto(1, OrderStatus.SHIPPED, email_log_id=7) == "stale"
        assert orders.storage[1].status == OrderStatus.IN_FLIGHT
        assert history.entries == []

    async def test_terminal_untouched(self, service, orders):
        orders.seed(make_order(id=1, status=OrderStatus.CANCELLED))
        assert (
            await service.advance_status_auto(1, OrderStatus.SHIPPED, email_log_id=7)
            == "terminal"
        )

    async def test_non_auto_target_rejected(self, service, orders):
        orders.seed(make_order(id=1, status=OrderStatus.PURCHASED))
        assert (
            await service.advance_status_auto(1, OrderStatus.DELIVERED, email_log_id=7)
            == "rejected"
        )
