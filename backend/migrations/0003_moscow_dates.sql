-- Календарные даты бизнеса считаются по Москве (Europe/Moscow), а не по UTC сервера:
-- дефолты «сегодня» для purchased_on и paid_on переводим с CURRENT_DATE (UTC)
-- на московскую дату. Сервисы обычно передают дату явно, дефолт — страховка.
ALTER TABLE orders
    ALTER COLUMN purchased_on SET DEFAULT ((now() AT TIME ZONE 'Europe/Moscow')::date);

ALTER TABLE payments
    ALTER COLUMN paid_on SET DEFAULT ((now() AT TIME ZONE 'Europe/Moscow')::date);
