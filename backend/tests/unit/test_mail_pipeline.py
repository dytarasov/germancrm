"""Конвейер обработки писем на фейках: LLM замокан, матчинг и статусы реальные."""

from decimal import Decimal

import pytest

from crm.application.interfaces.llm import LLMUnavailableError
from crm.application.services.mail_service import MailService
from crm.application.services.matching import MatcherService
from crm.application.services.order_service import OrderService
from crm.domain.enums import (
    EmailEventType,
    EmailProcessingStatus,
    OrderStatus,
    TrackMatchStatus,
)
from crm.domain.models import EmailExtraction, ExtractedTrack, LLMUsage
from tests.unit.fakes import (
    NOW,
    FakeEmailRepository,
    FakeGmailStateRepository,
    FakeOrderItemRepository,
    FakeOrderRepository,
    FakePaymentRepository,
    FakeSettingsRepository,
    FakeStatusHistoryRepository,
    FakeTrackRepository,
    FakeUnitOfWork,
    make_order,
)


class StubLLM:
    def __init__(self, extraction: EmailExtraction | None = None, error: Exception | None = None):
        self.extraction = extraction
        self.error = error
        self.calls = 0

    async def extract(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        usage = LLMUsage(
            model="test/model",
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=Decimal("0.001"),
            attempts=1,
        )
        return self.extraction, usage

    async def ping(self) -> str:
        return "test/model"


def shipped_extraction(track="1Z999AA10123456784", confidence=0.95) -> EmailExtraction:
    return EmailExtraction(
        event_type=EmailEventType.SHIPPED,
        confidence=confidence,
        store_domain="amazon.com",
        order_number=None,
        tracking_numbers=[ExtractedTrack(number=track, carrier="ups")],
        carrier="ups",
        summary="Amazon отправил посылку",
    )


def make_env():
    class Env:
        orders = FakeOrderRepository()
        tracks = FakeTrackRepository()
        emails = FakeEmailRepository()
        gmail_state = FakeGmailStateRepository()
        settings = FakeSettingsRepository(
            {"matching.auto_threshold": 80, "mail.whitelist_domains": ["amazon.com"]}
        )
        history = FakeStatusHistoryRepository()

        def mail_service(self, llm) -> MailService:
            order_service = OrderService(
                self.orders,
                FakeOrderItemRepository(),
                self.tracks,
                FakePaymentRepository(),
                self.history,
                self.settings,
                FakeUnitOfWork(),
            )
            return MailService(
                gmail=None,  # ingest в этих тестах не трогаем
                gmail_state=self.gmail_state,
                emails=self.emails,
                settings=self.settings,
                orders=self.orders,
                tracks=self.tracks,
                order_service=order_service,
                matcher=MatcherService(),
                llm=llm,
                uow=FakeUnitOfWork(),
                gmail_configured=True,
            )

    return Env()


@pytest.fixture
def env():
    return make_env()


async def test_confident_shipped_creates_track_and_advances(env):
    env.orders.seed(make_order(id=1, store="Amazon", status=OrderStatus.PURCHASED))
    body = "Your package: 1Z999AA10123456784"
    env.emails.seed_entry(id=10, body_text=body)
    svc = env.mail_service(StubLLM(shipped_extraction()))

    stats = await svc.process_cycle(now=NOW)

    assert stats.processed == 1
    assert env.orders.storage[1].status == OrderStatus.SHIPPED
    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track is not None and track.order_id == 1
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED
    actions = [e["action"] for e in env.emails.events]
    assert "track_added" in [str(a) for a in actions]
    assert "status_advanced" in [str(a) for a in actions]


async def test_ambiguous_shipped_creates_open_track_with_candidates(env):
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.orders.seed(make_order(id=2, store="Amazon"))
    env.emails.seed_entry(id=10, body_text="Track 1Z999AA10123456784")
    svc = env.mail_service(StubLLM(shipped_extraction()))

    await svc.process_cycle(now=NOW)

    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track is not None
    assert track.order_id is None
    assert track.match_status == TrackMatchStatus.OPEN
    assert track.candidates and len(track.candidates) >= 2
    # никого не двигаем
    assert env.orders.storage[1].status == OrderStatus.PURCHASED
    assert env.orders.storage[2].status == OrderStatus.PURCHASED


async def test_hallucinated_track_goes_to_manual_review(env):
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.emails.seed_entry(id=10, body_text="Письмо без номера вообще")
    svc = env.mail_service(StubLLM(shipped_extraction()))

    stats = await svc.process_cycle(now=NOW)

    assert stats.manual == 1
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.MANUAL_REVIEW
    assert await env.tracks.get_by_number("1Z999AA10123456784") is None


async def test_llm_unavailable_leaves_pending(env):
    env.emails.seed_entry(id=10, body_text="x")
    svc = env.mail_service(StubLLM(error=LLMUnavailableError("нет ключа")))

    stats = await svc.process_cycle(now=NOW)

    assert stats.pending_llm == 1
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PENDING_LLM
    assert env.emails.storage[10].attempts == 0  # не вина письма


async def test_cancellation_email_never_touches_status(env):
    env.orders.seed(make_order(id=1, store="Amazon", status=OrderStatus.SHIPPED))
    env.emails.seed_entry(id=10, body_text="Your order was cancelled")
    extraction = EmailExtraction(
        event_type=EmailEventType.CANCELLATION_OR_REFUND,
        confidence=0.99,
        store_domain="amazon.com",
        order_number=None,
        tracking_numbers=[],
        carrier=None,
        summary="Отмена заказа",
    )
    svc = env.mail_service(StubLLM(extraction))

    await svc.process_cycle(now=NOW)

    assert env.orders.storage[1].status == OrderStatus.SHIPPED
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.MANUAL_REVIEW


async def test_warehouse_email_by_known_track(env):
    env.orders.seed(make_order(id=1, store="Amazon", status=OrderStatus.SHIPPED))
    await env.tracks.add(
        tracking_number="1Z999AA10123456784",
        carrier="ups",
        order_id=1,
        source="email",
        email_log_id=None,
        match_status="linked",
        candidates=None,
        note=None,
    )
    env.emails.seed_entry(
        id=11,
        from_addr="notify@myforwarder.com",
        from_domain="myforwarder.com",
        body_text="Package received: 1Z999AA10123456784",
    )
    extraction = EmailExtraction(
        event_type=EmailEventType.ARRIVED_AT_WAREHOUSE,
        confidence=0.9,
        store_domain=None,
        order_number=None,
        tracking_numbers=[ExtractedTrack(number="1Z999AA10123456784", carrier="ups")],
        carrier="ups",
        summary="Посылка на складе",
    )
    svc = env.mail_service(StubLLM(extraction))

    await svc.process_cycle(now=NOW)

    assert env.orders.storage[1].status == OrderStatus.AT_WAREHOUSE


async def test_processing_error_backoff_then_poison(env):
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.emails.seed_entry(id=10, body_text="Track 1Z999AA10123456784", attempts=4)

    class BrokenTracks(FakeTrackRepository):
        async def get_by_number(self, tracking_number):
            raise RuntimeError("боль")

    env.tracks = BrokenTracks()
    svc = env.mail_service(StubLLM(shipped_extraction()))

    stats = await svc.process_cycle(now=NOW)

    assert stats.failed == 1
    entry = env.emails.storage[10]
    assert entry.processing_status == EmailProcessingStatus.POISON
    assert entry.attempts == 5


async def test_order_number_only_in_subject_survives_guard(env):
    """Номер заказа часто лежит только в теме письма — guard обязан искать и там."""
    env.orders.seed(make_order(id=1, store="Amazon", store_order_number=None))
    env.emails.seed_entry(
        id=10,
        subject="Your order 113-1234567-1234567 has been confirmed",
        body_text="Thanks for shopping with us!",
    )
    extraction = EmailExtraction(
        event_type=EmailEventType.ORDER_CONFIRMATION,
        confidence=0.95,
        store_domain="amazon.com",
        order_number="113-1234567-1234567",
        tracking_numbers=[],
        carrier=None,
        summary="Подтверждение заказа",
    )
    svc = env.mail_service(StubLLM(extraction))

    await svc.process_cycle(now=NOW)

    assert env.orders.storage[1].store_order_number == "113-1234567-1234567"


async def test_dismissed_track_not_resurrected_by_automation(env):
    """Человек пометил трек «не относится» — автоматика решение не отменяет."""
    env.orders.seed(make_order(id=1, store="Amazon"))
    await env.tracks.add(
        tracking_number="1Z999AA10123456784",
        carrier="ups",
        order_id=None,
        source="email",
        email_log_id=None,
        match_status="dismissed",
        candidates=None,
        note=None,
    )
    env.emails.seed_entry(id=10, body_text="Track 1Z999AA10123456784")
    svc = env.mail_service(StubLLM(shipped_extraction()))

    await svc.process_cycle(now=NOW)

    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track.match_status == TrackMatchStatus.DISMISSED
    assert track.order_id is None
    assert env.orders.storage[1].status == OrderStatus.PURCHASED


async def test_unexpected_llm_crash_does_not_stall_queue(env):
    """Неожиданное исключение из llm.extract — backoff письму, хвост очереди живёт."""
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.emails.seed_entry(id=10, body_text="x")
    env.emails.seed_entry(id=11, body_text="y")

    class CrashingLLM(StubLLM):
        async def extract(self, **kwargs):
            raise RuntimeError("боль в json")

    stats = env.mail_service(CrashingLLM()).process_cycle(now=NOW)
    stats = await stats

    assert stats.failed == 2  # оба письма зарегистрированы, цикл не упал
    assert env.emails.storage[10].attempts == 1
    assert env.emails.storage[10].next_attempt_at is not None
    assert env.emails.storage[11].attempts == 1


async def test_email_resolved_during_llm_call_not_applied_twice(env):
    """Гонка: пока LLM думал, письмо разобрали вручную — второй раз не применяем."""
    env.orders.seed(make_order(id=1, store="Amazon", status=OrderStatus.PURCHASED))
    env.emails.seed_entry(id=10, body_text="Track 1Z999AA10123456784")

    emails = env.emails

    class ResolvingLLM(StubLLM):
        async def extract(self, **kwargs):
            # симулируем ручной resolve, случившийся во время LLM-вызова
            await emails.update(10, {"processing_status": EmailProcessingStatus.PROCESSED})
            return await super().extract(**kwargs)

    svc = env.mail_service(ResolvingLLM(shipped_extraction()))
    await svc.process_cycle(now=NOW)

    # автоматика не применила письмо поверх ручного разбора
    assert env.orders.storage[1].status == OrderStatus.PURCHASED
    assert await env.tracks.get_by_number("1Z999AA10123456784") is None
    assert env.emails.storage[10].processing_status == EmailProcessingStatus.PROCESSED


async def test_low_confidence_no_auto_actions(env):
    env.orders.seed(make_order(id=1, store="Amazon"))
    env.emails.seed_entry(id=10, body_text="Track 1Z999AA10123456784")
    svc = env.mail_service(StubLLM(shipped_extraction(confidence=0.5)))

    await svc.process_cycle(now=NOW)

    track = await env.tracks.get_by_number("1Z999AA10123456784")
    assert track is not None and track.order_id is None
    assert env.orders.storage[1].status == OrderStatus.PURCHASED


async def test_retro_match_refreshes_stale_candidates(env):
    """Заказ, созданный ПОСЛЕ письма, появляется в подсказках старого трека,
    а протухшие кандидаты пересчитываются (контекст письма сохраняется)."""
    env.emails.seed_entry(
        id=10,
        body_text="Track 1ZNIKE1234567890AB",
        extracted={"store_domain": "nike.com", "order_number": None},
    )
    await env.tracks.add(
        tracking_number="1ZNIKE1234567890AB",
        carrier="ups",
        order_id=None,
        source="email",
        email_log_id=10,
        match_status="open",
        candidates=[{"order_id": 999, "score": 45, "reasons": ["устаревший расчёт"], "order_label": "Заказ #999"}],
        note=None,
    )
    env.orders.seed(make_order(id=7, store="Nike"))
    svc = env.mail_service(StubLLM())

    refreshed = await svc.retro_match()

    assert refreshed == 1
    track = await env.tracks.get_by_number("1ZNIKE1234567890AB")
    ids = [c.order_id for c in track.candidates]
    assert 7 in ids, "новый Nike-заказ должен попасть в подсказки"
    assert 999 not in ids, "протухшие кандидаты пересчитаны заново"
