from datetime import date
from decimal import Decimal

import pytest

from crm.domain import rules
from crm.domain.enums import OrderStatus
from crm.domain.exceptions import CommissionRequiredError


def test_flow_order():
    assert rules.flow_index(OrderStatus.PURCHASED) < rules.flow_index(OrderStatus.SHIPPED)
    assert rules.flow_index(OrderStatus.DELIVERED) < rules.flow_index(OrderStatus.CLOSED)
    assert rules.flow_index(OrderStatus.CANCELLED) == -1


def test_terminal():
    assert rules.is_terminal(OrderStatus.CLOSED)
    assert rules.is_terminal(OrderStatus.CANCELLED)
    assert rules.is_terminal(OrderStatus.REFUNDED)
    assert not rules.is_terminal(OrderStatus.DELIVERED)


class TestAutoAdvance:
    def test_forward_to_shipped(self):
        assert rules.can_auto_advance(OrderStatus.PURCHASED, OrderStatus.SHIPPED)

    def test_skip_forward_to_warehouse(self):
        # письмо склада пришло раньше письма магазина — валидный прыжок вперёд
        assert rules.can_auto_advance(OrderStatus.PURCHASED, OrderStatus.AT_WAREHOUSE)

    def test_never_backward(self):
        assert not rules.can_auto_advance(OrderStatus.AT_WAREHOUSE, OrderStatus.SHIPPED)
        assert not rules.can_auto_advance(OrderStatus.SHIPPED, OrderStatus.SHIPPED)

    def test_never_touches_terminal(self):
        assert not rules.can_auto_advance(OrderStatus.CANCELLED, OrderStatus.SHIPPED)
        assert not rules.can_auto_advance(OrderStatus.CLOSED, OrderStatus.SHIPPED)
        assert not rules.can_auto_advance(OrderStatus.REFUNDED, OrderStatus.AT_WAREHOUSE)

    def test_only_auto_targets(self):
        assert not rules.can_auto_advance(OrderStatus.PURCHASED, OrderStatus.IN_FLIGHT)
        assert not rules.can_auto_advance(OrderStatus.PURCHASED, OrderStatus.CLOSED)
        assert not rules.can_auto_advance(OrderStatus.PURCHASED, OrderStatus.DELIVERED)


class TestCommission:
    def test_null_commission_blocks_close(self):
        with pytest.raises(CommissionRequiredError):
            rules.ensure_closable(None)

    def test_zero_commission_is_valid(self):
        # 0 = «везу без наценки» — это НЕ отсутствие комиссии
        rules.ensure_closable(Decimal("0"))

    def test_suggested_commission(self):
        assert rules.suggest_commission(Decimal("2.5")) == Decimal("125.00")
        assert rules.suggest_commission(Decimal("0.454")) == Decimal("22.70")
        assert rules.suggest_commission(Decimal("2"), Decimal("65")) == Decimal("130.00")


class TestOverdue:
    def test_overdue_before_delivery(self):
        assert rules.is_overdue(OrderStatus.IN_FLIGHT, date(2026, 8, 1), date(2026, 8, 6))

    def test_not_overdue_when_delivered(self):
        assert not rules.is_overdue(OrderStatus.DELIVERED, date(2026, 8, 1), date(2026, 8, 6))

    def test_not_overdue_without_date(self):
        assert not rules.is_overdue(OrderStatus.PURCHASED, None, date(2026, 8, 6))

    def test_not_overdue_same_day(self):
        assert not rules.is_overdue(OrderStatus.PURCHASED, date(2026, 8, 6), date(2026, 8, 6))


def test_money_math():
    assert rules.revenue_usd(Decimal("100"), None) is None
    assert rules.revenue_usd(Decimal("100"), Decimal("50")) == Decimal("150")
    assert rules.due_usd(Decimal("100"), None, Decimal("30")) is None
    assert rules.due_usd(Decimal("100"), Decimal("50"), Decimal("30")) == Decimal("120")


def test_due_is_zero_for_closed_only():
    args = (Decimal("100"), Decimal("50"), Decimal("30"))
    assert rules.due_usd(*args, OrderStatus.CLOSED) == Decimal("0")
    # переоткрытый заказ снова показывает остаток
    assert rules.due_usd(*args, OrderStatus.DELIVERED) == Decimal("120")
    assert rules.due_usd(*args, OrderStatus.CANCELLED) == Decimal("120")
