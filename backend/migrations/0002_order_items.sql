-- Позиции заказа: составная покупка внутри ОДНОГО магазина.
-- Позиция = название и/или ссылка (можно кинуть только URL — «массив ссылок»).
-- Цена закупки остаётся на заказе (один чек), по позициям не размазывается.

CREATE TABLE order_items (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    title      TEXT,
    url        TEXT,
    quantity   INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_item_has_content CHECK (title IS NOT NULL OR url IS NOT NULL)
);

CREATE INDEX idx_order_items_order ON order_items (order_id);
