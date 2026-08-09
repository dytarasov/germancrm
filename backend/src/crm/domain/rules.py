"""Доменные правила жизненного цикла заказа и денег."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from crm.domain.enums import OrderStatus
from crm.domain.exceptions import CommissionRequiredError

# Линейный путь заказа; терминальные cancelled/refunded — вне линейки.
STATUS_FLOW: list[OrderStatus] = [
    OrderStatus.PURCHASED,
    OrderStatus.SHIPPED,
    OrderStatus.AT_WAREHOUSE,
    OrderStatus.IN_FLIGHT,
    OrderStatus.DELIVERED,
    OrderStatus.CLOSED,
]

TERMINAL_STATUSES = {OrderStatus.CLOSED, OrderStatus.CANCELLED, OrderStatus.REFUNDED}
ACTIVE_STATUSES = {
    OrderStatus.PURCHASED,
    OrderStatus.SHIPPED,
    OrderStatus.AT_WAREHOUSE,
    OrderStatus.IN_FLIGHT,
    OrderStatus.DELIVERED,
}
# Просрочка возможна, только пока заказ не у клиента.
OVERDUE_STATUSES = {
    OrderStatus.PURCHASED,
    OrderStatus.SHIPPED,
    OrderStatus.AT_WAREHOUSE,
    OrderStatus.IN_FLIGHT,
}
# Автоматика умеет двигать только сюда.
AUTO_TARGETS = {OrderStatus.SHIPPED, OrderStatus.AT_WAREHOUSE}

# Дефолт тарифа; рабочее значение живёт в настройках (commission.per_kg_usd).
COMMISSION_PER_KG_USD = Decimal("50")
_CENT = Decimal("0.01")


def flow_index(status: OrderStatus) -> int:
    try:
        return STATUS_FLOW.index(status)
    except ValueError:
        return -1


def is_terminal(status: OrderStatus) -> bool:
    return status in TERMINAL_STATUSES


def ensure_closable(commission_usd: Decimal | None) -> None:
    if commission_usd is None:
        raise CommissionRequiredError()


def can_auto_advance(current: OrderStatus, new: OrderStatus) -> bool:
    """Автоматика: только вперёд, только в AUTO_TARGETS, терминальные не трогаем."""
    if current in TERMINAL_STATUSES or new not in AUTO_TARGETS:
        return False
    return flow_index(new) > flow_index(current) >= 0


def suggest_commission(
    weight_kg: Decimal, per_kg_usd: Decimal = COMMISSION_PER_KG_USD
) -> Decimal:
    return (weight_kg * per_kg_usd).quantize(_CENT)


def is_overdue(status: OrderStatus, promised_date: date | None, today: date) -> bool:
    return promised_date is not None and status in OVERDUE_STATUSES and promised_date < today


def revenue_usd(purchase_price_usd: Decimal, commission_usd: Decimal | None) -> Decimal | None:
    if commission_usd is None:
        return None
    return purchase_price_usd + commission_usd


def due_usd(
    purchase_price_usd: Decimal, commission_usd: Decimal | None, paid_usd: Decimal
) -> Decimal | None:
    revenue = revenue_usd(purchase_price_usd, commission_usd)
    if revenue is None:
        return None
    return revenue - paid_usd
