from crm.application.services.mail_service import domain_in_list, guard_extraction
from crm.domain.enums import EmailEventType
from crm.domain.models import EmailExtraction, ExtractedTrack


def make_extraction(**overrides) -> EmailExtraction:
    defaults = dict(
        event_type=EmailEventType.SHIPPED,
        confidence=0.9,
        store_domain="amazon.com",
        order_number="113-1234567-1234567",
        tracking_numbers=[ExtractedTrack(number="1Z999AA10123456784", carrier="ups")],
        carrier="ups",
        summary="Заказ отправлен",
    )
    defaults.update(overrides)
    return EmailExtraction(**defaults)


def test_keeps_present_track():
    body = "Your package is on the way! Tracking: 1Z999AA10123456784"
    e = guard_extraction(make_extraction(), body)
    assert len(e.tracking_numbers) == 1


def test_drops_hallucinated_track():
    body = "Your package is on the way, no tracking available yet."
    e = guard_extraction(make_extraction(order_number=None), body)
    assert e.tracking_numbers == []


def test_finds_track_inside_link_with_spaces():
    # номер разбит пробелами/дефисами и лежит в URL — нормализация должна его найти
    body = "Track: https://www.ups.com/track?tracknum=1Z-999-AA1-0123456784&loc=en_US"
    e = guard_extraction(make_extraction(order_number=None), body)
    assert len(e.tracking_numbers) == 1


def test_drops_hallucinated_order_number():
    body = "Thanks for your purchase! Tracking: 1Z999AA10123456784"
    e = guard_extraction(make_extraction(), body)
    assert e.order_number is None
    assert len(e.tracking_numbers) == 1


def test_keeps_present_order_number():
    body = "Order 113-1234567-1234567 confirmed"
    e = guard_extraction(make_extraction(tracking_numbers=[]), body)
    assert e.order_number == "113-1234567-1234567"


def test_domain_whitelist_suffix_match():
    allowed = ["amazon.com", "usps.com"]
    assert domain_in_list("amazon.com", allowed)
    assert domain_in_list("shipment-tracking.amazon.com", allowed)
    assert domain_in_list("informeddelivery.usps.com", allowed)
    assert not domain_in_list("amazon.com.evil.ru", allowed)
    assert not domain_in_list("notamazon.com", allowed)
