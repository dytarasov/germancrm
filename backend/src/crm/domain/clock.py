"""Бизнес-календарь: заказчик живёт по Москве, поэтому «сегодня», отчётные
месяцы и просрочка считаются по Europe/Moscow, а не по UTC сервера.
Абсолютные моменты (created_at, closed_at и т.п.) остаются TIMESTAMPTZ в UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("Europe/Moscow")

# SQL-эквивалент business_today() для чистых запросов в репозиториях.
SQL_BUSINESS_TODAY = "(now() AT TIME ZONE 'Europe/Moscow')::date"


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()
