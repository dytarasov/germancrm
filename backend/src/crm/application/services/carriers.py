"""Детерминированное определение перевозчика по формату трек-номера.

Это НЕ классификация писем (она за LLM) — это пост-обработка качества данных:
нормализованный номер либо соответствует известному формату, либо помечается
неправдоподобным и отбрасывается до попадания в БД."""

from __future__ import annotations

import re

# Порядок важен: специфичные форматы раньше «голых цифр».
CARRIER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ups", re.compile(r"^1Z[A-Z0-9]{16}$")),
    ("amazon_logistics", re.compile(r"^TBA\d{9,15}$")),
    ("usps", re.compile(r"^9[2-5]\d{19,24}$")),
    ("usps", re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$")),  # UPU S10: EA123456789US
    ("dhl", re.compile(r"^\d{10}$")),
    ("fedex", re.compile(r"^(\d{12}|\d{15}|\d{20,22})$")),
]

_PLAUSIBLE_RE = re.compile(r"^[A-Z0-9]{8,40}$")


def infer_carrier(normalized_number: str) -> str | None:
    for carrier, pattern in CARRIER_PATTERNS:
        if pattern.match(normalized_number):
            return carrier
    return None


def is_plausible_tracking_number(normalized_number: str) -> bool:
    """Трек — 8..40 символов A-Z/0-9 и содержит хотя бы одну цифру."""
    return bool(
        _PLAUSIBLE_RE.match(normalized_number)
        and any(ch.isdigit() for ch in normalized_number)
    )
