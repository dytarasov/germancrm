"""Ручной разбор письма из очереди: привязка к заказу, треки, событие."""


import pytest

from crm.domain.enums import (
    EmailEventType,
    EmailProcessingStatus,
    OrderStatus,
    StatusSource,
    TrackMatchStatus,
)
from crm.domain.exceptions import DomainValidationError, NotFoundError
from tests.unit.fakes import make_order
from tests.unit.test_mail_pipeline import StubLLM, make_env


@pytest.fixture
def env():
    return make_env()


def service(env):
    return env.mail_service(StubLLM())


async def test_resolve_creates_track_and_advances_as_manual(env):
    env.orders.seed(make_order(id=1, store="Amazon", status=OrderStatus.PURCHASED))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.MANUAL_REVIEW)
    svc = service(env)

    await svc.resolve_email(
        10,
        order_id=1,
        event_type=EmailEventType.SHIPPED,
        tracking_numbers=["1z 999 aa1 0123 456 784"],
        carrier="ups",
    )

    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track is not None and track.order_id == 1
    assert env.orders.storage[1].status == OrderStatus.SHIPPED
    # решение принял человек — в истории source=manual со ссылкой на письмо
    assert env.history.entries[-1].source == StatusSource.MANUAL
    assert env.history.entries[-1].email_log_id == 10
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED


async def test_resolve_links_existing_open_track(env):
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.MANUAL_REVIEW)
    await env.tracks.add(
        tracking_number="1Z999AA10123456784",
        carrier=None,
        order_id=None,
        source="email",
        email_log_id=None,
        match_status="open",
        candidates=None,
        note=None,
    )
    svc = service(env)

    await svc.resolve_email(10, order_id=1, tracking_numbers=["1Z999AA10123456784"])

    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track.order_id == 1
    assert track.match_status == TrackMatchStatus.LINKED
    # событие не задано — статус не трогаем
    assert env.orders.storage[1].status == OrderStatus.PURCHASED


async def test_resolve_stale_event_does_not_move_backward(env):
    env.orders.seed(make_order(id=1, status=OrderStatus.IN_FLIGHT))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.POISON)
    svc = service(env)

    await svc.resolve_email(10, order_id=1, event_type=EmailEventType.SHIPPED)

    assert env.orders.storage[1].status == OrderStatus.IN_FLIGHT
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED
    outcomes = [e["details"].get("outcome") for e in env.emails.events if e.get("details")]
    assert "stale" in outcomes


async def test_resolve_rejects_wrong_event_and_missing_entities(env):
    env.orders.seed(make_order(id=1))
    env.emails.seed_entry(id=10)
    svc = service(env)

    with pytest.raises(DomainValidationError):
        await svc.resolve_email(10, order_id=1, event_type=EmailEventType.CANCELLATION_OR_REFUND)
    with pytest.raises(NotFoundError):
        await svc.resolve_email(999, order_id=1)
    with pytest.raises(NotFoundError):
        await svc.resolve_email(10, order_id=999)


async def test_resolve_processed_email_conflicts(env):
    from crm.domain.exceptions import ConflictError

    env.orders.seed(make_order(id=1))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.PROCESSED)
    svc = service(env)
    with pytest.raises(ConflictError):
        await svc.resolve_email(10, order_id=1)


async def test_resolve_blank_tracks_fall_back_to_info(env):
    """[" "] нормализуется в пустоту — письмо не должно закрыться «в никуда»."""
    env.orders.seed(make_order(id=1))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.MANUAL_REVIEW)
    svc = service(env)

    await svc.resolve_email(10, order_id=1, tracking_numbers=["  ", "-"])

    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED
    assert str(env.emails.events[-1]["action"]) == "info"


async def test_resolve_dashed_input_links_existing_track(env):
    """Оператор вводит трек с дефисами «как в письме» — дубль не создаётся."""
    env.orders.seed(make_order(id=1))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.MANUAL_REVIEW)
    await env.tracks.add(
        tracking_number="1Z999AA10123456784",
        carrier=None,
        order_id=None,
        source="email",
        email_log_id=None,
        match_status="open",
        candidates=None,
        note=None,
    )
    svc = service(env)

    await svc.resolve_email(10, order_id=1, tracking_numbers=["1Z-999-AA1-0123456784"])

    assert len(env.tracks.storage) == 1  # привязали существующий, не создали второй
    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track.order_id == 1


async def test_resolve_without_event_and_tracks_marks_info(env):
    env.orders.seed(make_order(id=1))
    env.emails.seed_entry(id=10, processing_status=EmailProcessingStatus.MANUAL_REVIEW)
    svc = service(env)

    await svc.resolve_email(10, order_id=1)

    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED
    assert env.emails.events[-1]["order_id"] == 1
    assert str(env.emails.events[-1]["action"]) == "info"
