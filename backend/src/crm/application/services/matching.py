"""Скоринг «событие/трек → заказ». Используется почтовым конвейером и подсказками треков."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from crm.domain import rules
from crm.domain.clock import business_today
from crm.domain.enums import OrderStatus
from crm.domain.models import OrderListRow

# Только буквы и цифры: реальные номера приезжают с пробелами, дефисами и даже
# невидимыми символами (U+202B из буфера обмена) — всё это не должно ломать
# точное совпадение. SQL-эквивалент — в suborder_repo и индексе 0006.
_NORM_RE = re.compile(r"[^0-9A-Za-z]+")


def normalize_number(value: str) -> str:
    return _NORM_RE.sub("", value).upper()


def order_label(row: OrderListRow) -> str:
    return f"Заказ #{row.order.id} · {row.client_name} · {row.order.store}"


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    row: OrderListRow
    score: int
    reasons: list[str]


class MatcherService:
    """Чистый скоринг без I/O: кандидатов загружает вызывающая сторона."""

    def score_orders(
        self,
        candidates: list[OrderListRow],
        *,
        store_domain: str | None = None,
        order_number: str | None = None,
        target_status: OrderStatus | None = None,
        today: date | None = None,
    ) -> list[MatchCandidate]:
        today = today or business_today()
        norm_number = normalize_number(order_number) if order_number else None
        store_token = _store_token(store_domain)

        store_matches = [
            r for r in candidates if store_token and _store_hit(store_token, r.order.store)
        ]
        single_store_order_id = store_matches[0].order.id if len(store_matches) == 1 else None

        scored: list[MatchCandidate] = []
        for row in candidates:
            order = row.order
            score = 0
            reasons: list[str] = []

            if norm_number and any(
                normalize_number(n) == norm_number for n in row.order_numbers
            ):
                score += 100
                reasons.append("совпал номер заказа магазина")

            if store_token and _store_hit(store_token, order.store):
                score += 30
                reasons.append("магазин совпадает")

            if order.id == single_store_order_id:
                score += 25
                reasons.append("единственный активный заказ этого магазина")

            if target_status is not None:
                if rules.flow_index(order.status) < rules.flow_index(target_status):
                    score += 20
                    reasons.append("статус допускает переход")
                else:
                    score -= 50
                    reasons.append("заказ уже дальше по статусу")
            elif order.status in (OrderStatus.PURCHASED, OrderStatus.SHIPPED):
                score += 20
                reasons.append("статус допускает привязку трека")

            if row.tracks_count == 0:
                score += 15
                reasons.append("у заказа ещё нет треков")

            age_days = (today - order.purchased_on).days
            if age_days < 0:
                # заказ создан ПОЗЖЕ письма — письмо не может быть о нём
                score -= 30
                reasons.append("заказ создан позже письма")
            elif age_days <= 14:
                score += 10
                reasons.append("куплен недавно")
            elif age_days <= 45:
                score += 5
                reasons.append("куплен в последние 45 дней")

            if score > 0:
                scored.append(MatchCandidate(row=row, score=score, reasons=reasons))

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored

    @staticmethod
    def is_confident(
        scored: list[MatchCandidate], *, auto_threshold: int, min_gap: int = 20
    ) -> bool:
        if not scored or scored[0].score < auto_threshold:
            return False
        if len(scored) == 1:
            return True
        return scored[0].score - scored[1].score >= min_gap


def _store_token(store_domain: str | None) -> str | None:
    """amazon.com -> amazon; сравниваем с свободным текстом поля store."""
    if not store_domain:
        return None
    return store_domain.split(".")[0].lower() or None


def _store_hit(store_token: str, store_field: str) -> bool:
    return store_token in store_field.lower()
