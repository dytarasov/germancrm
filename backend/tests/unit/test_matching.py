from datetime import timedelta
from decimal import Decimal

from crm.application.services.matching import MatcherService, normalize_number
from crm.domain.enums import OrderStatus
from crm.domain.models import OrderListRow
from tests.unit.fakes import TODAY, make_order


def row(order, client_name="Иванов", tracks_count=0, order_numbers=None) -> OrderListRow:
    return OrderListRow(
        order=order,
        client_name=client_name,
        paid_usd=Decimal("0"),
        tracks_count=tracks_count,
        suborders_count=1,
        order_numbers=order_numbers or [],
    )


def test_normalize_number():
    assert normalize_number("113-1234567-1234567") == "11312345671234567"
    assert normalize_number("1z 999 aa1") == "1Z999AA1"
    # невидимый RTL-символ из буфера обмена (реальный случай с прода)
    assert normalize_number("‫112-0271351-5232215") == "11202713515232215"


def test_order_number_match_dominates():
    matcher = MatcherService()
    target = row(make_order(id=1), order_numbers=["113-1234567-1234567"])
    other = row(make_order(id=2, store="Amazon"))
    scored = matcher.score_orders(
        [other, target],
        store_domain="amazon.com",
        order_number="113-1234567-1234567",
        target_status=OrderStatus.SHIPPED,
        today=TODAY,
    )
    assert scored[0].row.order.id == 1
    assert scored[0].score >= 100
    assert matcher.is_confident(scored, auto_threshold=80)


def test_order_already_ahead_penalized():
    matcher = MatcherService()
    ahead = row(make_order(id=1, status=OrderStatus.DELIVERED))
    fresh = row(make_order(id=2, status=OrderStatus.PURCHASED))
    scored = matcher.score_orders(
        [ahead, fresh],
        store_domain="amazon.com",
        target_status=OrderStatus.SHIPPED,
        today=TODAY,
    )
    ids = [c.row.order.id for c in scored]
    assert ids[0] == 2


def test_single_store_order_bonus():
    matcher = MatcherService()
    amazon = row(make_order(id=1, store="Amazon"))
    ebay = row(make_order(id=2, store="eBay"))
    scored = matcher.score_orders(
        [amazon, ebay],
        store_domain="amazon.com",
        target_status=OrderStatus.SHIPPED,
        today=TODAY,
    )
    top = scored[0]
    assert top.row.order.id == 1
    assert "единственный активный заказ этого магазина" in top.reasons


def test_not_confident_when_scores_close():
    matcher = MatcherService()
    a = row(make_order(id=1, store="Amazon"))
    b = row(make_order(id=2, store="Amazon store"))
    scored = matcher.score_orders(
        [a, b],
        store_domain="amazon.com",
        target_status=OrderStatus.SHIPPED,
        today=TODAY,
    )
    # оба «amazon» — отрыв меньше 20, автопривязки быть не должно
    assert not matcher.is_confident(scored, auto_threshold=scored[0].score)


def test_old_orders_score_lower():
    matcher = MatcherService()
    fresh = row(make_order(id=1, purchased_on=TODAY - timedelta(days=3)))
    old = row(make_order(id=2, purchased_on=TODAY - timedelta(days=50)))
    scored = matcher.score_orders([old, fresh], today=TODAY)
    assert scored[0].row.order.id == 1
