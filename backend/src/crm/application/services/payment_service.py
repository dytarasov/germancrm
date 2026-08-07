from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from crm.application.interfaces.repositories import OrderRepository, PaymentRepository
from crm.application.interfaces.uow import UnitOfWork
from crm.domain.clock import business_today
from crm.domain.exceptions import DomainValidationError, NotFoundError
from crm.domain.models import Payment


class PaymentService:
    def __init__(
        self, payments: PaymentRepository, orders: OrderRepository, uow: UnitOfWork
    ) -> None:
        self._payments = payments
        self._orders = orders
        self._uow = uow

    async def add_to_order(
        self,
        order_id: int,
        *,
        amount_usd: Decimal,
        paid_on: date | None = None,
        comment: str | None = None,
    ) -> Payment:
        if amount_usd <= 0:
            raise DomainValidationError("Сумма платежа должна быть больше нуля")
        async with self._uow:
            if await self._orders.get(order_id) is None:
                raise NotFoundError.entity("Заказ", order_id)
            return await self._payments.add(
                order_id=order_id,
                paid_on=paid_on or business_today(),
                amount_usd=amount_usd,
                comment=comment,
            )

    async def list_for_order(self, order_id: int) -> list[Payment]:
        return await self._payments.list_for_order(order_id)

    async def list(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        client_id: int | None = None,
    ) -> list[Payment]:
        return await self._payments.list(date_from=date_from, date_to=date_to, client_id=client_id)

    async def update(self, payment_id: int, fields: dict[str, Any]) -> Payment:
        if "amount_usd" in fields and fields["amount_usd"] is not None and fields["amount_usd"] <= 0:
            raise DomainValidationError("Сумма платежа должна быть больше нуля")
        async with self._uow:
            payment = await self._payments.update(payment_id, fields)
        if payment is None:
            raise NotFoundError.entity("Платёж", payment_id)
        return payment

    async def delete(self, payment_id: int) -> None:
        async with self._uow:
            if await self._payments.get(payment_id) is None:
                raise NotFoundError.entity("Платёж", payment_id)
            await self._payments.delete(payment_id)
