"""Определение перевозчика по формату номера и чистка LLM-экстракции."""

from crm.application.services.carriers import infer_carrier, is_plausible_tracking_number
from crm.application.services.mail_service import enrich_extraction
from crm.domain.enums import EmailEventType
from crm.domain.models import EmailExtraction, ExtractedTrack
from crm.infrastructure.llm.prompt import build_system_prompt


class TestInferCarrier:
    def test_known_formats(self):
        assert infer_carrier("1Z999AA10123456784") == "ups"
        assert infer_carrier("9400111899223197428490") == "usps"
        assert infer_carrier("EA123456789US") == "usps"
        assert infer_carrier("TBA123456789012") == "amazon_logistics"
        assert infer_carrier("1234567890") == "dhl"
        assert infer_carrier("123456789012") == "fedex"

    def test_unknown_format(self):
        assert infer_carrier("ABC123XYZ") is None


class TestPlausibility:
    def test_plausible(self):
        assert is_plausible_tracking_number("1Z999AA10123456784")
        assert is_plausible_tracking_number("9400111899223197428490")

    def test_implausible(self):
        assert not is_plausible_tracking_number("1234567")  # слишком короткий
        assert not is_plausible_tracking_number("ORDERSHIPPED")  # нет цифр
        assert not is_plausible_tracking_number("A" * 41)  # слишком длинный
        assert not is_plausible_tracking_number("")


def make_extraction(tracks: list[ExtractedTrack]) -> EmailExtraction:
    return EmailExtraction(
        event_type=EmailEventType.SHIPPED,
        confidence=0.9,
        store_domain="amazon.com",
        order_number=None,
        tracking_numbers=tracks,
        carrier=None,
        summary="",
        reasoning="тест",
    )


class TestEnrich:
    def test_infers_carrier_and_normalizes(self):
        e = enrich_extraction(
            make_extraction([ExtractedTrack(number="1z 999 aa1 0123 456 784", carrier=None)])
        )
        assert e.tracking_numbers[0].number == "1Z999AA10123456784"
        assert e.tracking_numbers[0].carrier == "ups"
        assert e.reasoning == "тест"

    def test_keeps_explicit_carrier(self):
        e = enrich_extraction(
            make_extraction([ExtractedTrack(number="1234567890", carrier="DHL")])
        )
        assert e.tracking_numbers[0].carrier == "dhl"

    def test_drops_garbage(self):
        e = enrich_extraction(
            make_extraction(
                [
                    ExtractedTrack(number="TRACK YOUR ORDER", carrier=None),
                    ExtractedTrack(number="9400111899223197428490", carrier=None),
                ]
            )
        )
        assert len(e.tracking_numbers) == 1
        assert e.tracking_numbers[0].carrier == "usps"


class TestPromptBuilder:
    def test_includes_forwarder_context(self):
        prompt = build_system_prompt(
            store_domains=["amazon.com"], forwarder_domains=["mywarehouse.com"]
        )
        assert "mywarehouse.com" in prompt
        assert "arrived_at_warehouse" in prompt
        assert "amazon.com" in prompt
        assert "reasoning" in prompt

    def test_without_forwarder_is_conservative(self):
        prompt = build_system_prompt(store_domains=[], forwarder_domains=[])
        assert "не настроены" in prompt
