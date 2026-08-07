"""Доменные исключения. Ничего не знают про HTTP — маппинг на коды в presentation/errors.py."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code: str = "domain_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "not_found"

    @classmethod
    def entity(cls, entity: str, entity_id: object) -> NotFoundError:
        return cls(f"{entity} #{entity_id} не найден", {"id": entity_id})


class ConflictError(DomainError):
    code = "conflict"


class CommissionRequiredError(ConflictError):
    code = "commission_required"

    def __init__(self) -> None:
        super().__init__("Нельзя закрыть заказ без комиссии: заполните комиссию (0 — «без наценки»)")


class InvalidStatusTransitionError(ConflictError):
    code = "invalid_status_transition"


class EntityInUseError(ConflictError):
    code = "entity_in_use"


class DuplicateError(ConflictError):
    code = "duplicate"


class DomainValidationError(DomainError):
    code = "validation_error"


class AuthenticationError(DomainError):
    code = "unauthorized"

    def __init__(self, message: str = "Не авторизован") -> None:
        super().__init__(message)
