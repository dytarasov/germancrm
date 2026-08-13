-- Подзаказы: одна корзина (Amazon/eBay) при выкупе разбивается магазином на
-- несколько заказов с разными номерами и треками. Деньги (закупка, комиссия,
-- вес) остаются на заказе-корзине; подзаказ несёт номер, справочную сумму и
-- собственный статус исполнения. orders.status становится агрегатом (худший
-- из активных подзаказов), orders.store_order_number переезжает в suborders.

CREATE TABLE suborders (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id           BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    store_order_number TEXT,
    -- справочная сумма лота (для сверки отмен/возвратов); в финансах не участвует
    amount_usd         NUMERIC(12,2) CHECK (amount_usd >= 0),
    -- физический путь посылки; closed/refunded — терминальные статусы уровня заказа
    status             TEXT NOT NULL DEFAULT 'purchased'
        CHECK (status IN ('purchased','shipped','at_warehouse','in_flight',
                          'delivered','cancelled')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_suborders_order_id ON suborders (order_id);
-- точный поиск по номеру заказа магазина в канонической форме
-- (та же нормализация, что normalize_number в Python: только буквы/цифры, upper —
-- реальные номера приезжают даже с невидимыми символами из буфера обмена)
CREATE INDEX idx_suborders_number_norm
    ON suborders (upper(regexp_replace(store_order_number, '[^a-zA-Z0-9]+', '', 'g')))
    WHERE store_order_number IS NOT NULL;

-- каждый существующий заказ получает ровно один подзаказ со своим номером и статусом
INSERT INTO suborders (order_id, store_order_number, status, created_at, updated_at)
SELECT id, store_order_number,
       CASE status
           WHEN 'closed'   THEN 'delivered'  -- физический путь завершён
           WHEN 'refunded' THEN 'cancelled'
           ELSE status
       END,
       created_at, updated_at
FROM orders;

-- трек принадлежит конкретному подзаказу (отправлению); NULL = подзаказ неизвестен
ALTER TABLE tracks ADD COLUMN suborder_id BIGINT REFERENCES suborders(id) ON DELETE SET NULL;
CREATE INDEX idx_tracks_suborder_id ON tracks (suborder_id) WHERE suborder_id IS NOT NULL;
UPDATE tracks t SET suborder_id = s.id FROM suborders s WHERE s.order_id = t.order_id;

-- история статусов: смены уровня подзаказа помечаются его id
ALTER TABLE order_status_history
    ADD COLUMN suborder_id BIGINT REFERENCES suborders(id) ON DELETE SET NULL;

ALTER TABLE orders DROP COLUMN store_order_number;
