-- germancrm: полная начальная схема.
-- Деньги NUMERIC(12,2) USD; время TIMESTAMPTZ; бизнес-даты DATE.
-- Статусы TEXT + CHECK (не ENUM: проще менять миграцией).

-- ############ clients ############
CREATE TABLE clients (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         TEXT NOT NULL,
    contacts     TEXT,
    telegram_url TEXT,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_clients_name ON clients (lower(name));

-- ############ flights ############
-- Рейс США -> Москва. Стоимость относится к периоду целиком, по заказам не размазывается.
CREATE TABLE flights (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    departed_on DATE NOT NULL,
    cost_usd    NUMERIC(12,2) NOT NULL CHECK (cost_usd >= 0),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_flights_departed_on ON flights (departed_on);

-- ############ orders ############
CREATE TABLE orders (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id           BIGINT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    store               TEXT NOT NULL,
    store_order_number  TEXT,
    items               TEXT NOT NULL,
    purchase_price_usd  NUMERIC(12,2) NOT NULL CHECK (purchase_price_usd >= 0),
    -- NULL = «ещё не знаю», 0 = «везу без наценки» — это разные вещи
    commission_usd      NUMERIC(12,2) CHECK (commission_usd >= 0),
    weight_kg           NUMERIC(8,3) CHECK (weight_kg >= 0),
    weight_is_final     BOOLEAN NOT NULL DEFAULT FALSE,
    promised_date       DATE,
    comment             TEXT,
    status              TEXT NOT NULL DEFAULT 'purchased'
        CHECK (status IN ('purchased','shipped','at_warehouse','in_flight',
                          'delivered','closed','cancelled','refunded')),
    refunded_amount_usd NUMERIC(12,2) CHECK (refunded_amount_usd >= 0),
    refunded_at         TIMESTAMPTZ,
    flight_id           BIGINT REFERENCES flights(id) ON DELETE SET NULL,
    copied_from         BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    purchased_on        DATE NOT NULL DEFAULT CURRENT_DATE,
    closed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- страховка доменных правил (первичная валидация — в сервисах)
    CONSTRAINT chk_closed_requires_commission
        CHECK (status <> 'closed' OR commission_usd IS NOT NULL),
    CONSTRAINT chk_closed_has_closed_at
        CHECK ((status = 'closed') = (closed_at IS NOT NULL)),
    CONSTRAINT chk_refund_requires_amount
        CHECK (status <> 'refunded' OR refunded_amount_usd IS NOT NULL),
    CONSTRAINT chk_refund_has_refunded_at
        CHECK ((status = 'refunded') = (refunded_at IS NOT NULL))
);
CREATE INDEX idx_orders_client_id ON orders (client_id);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_orders_active ON orders (id)
    WHERE status NOT IN ('closed','cancelled','refunded');
CREATE INDEX idx_orders_overdue ON orders (promised_date)
    WHERE status IN ('purchased','shipped','at_warehouse','in_flight');
CREATE INDEX idx_orders_closed_at ON orders (closed_at) WHERE closed_at IS NOT NULL;
CREATE INDEX idx_orders_flight_id ON orders (flight_id) WHERE flight_id IS NOT NULL;

-- ############ email_log ############
-- Журнал писем Gmail: и лог, и очередь обработки (двухфазный конвейер).
CREATE TABLE email_log (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gmail_message_id      TEXT NOT NULL UNIQUE,
    gmail_thread_id       TEXT,
    message_id_hdr        TEXT,
    from_addr             TEXT NOT NULL,
    from_domain           TEXT NOT NULL,
    subject               TEXT,
    sent_at               TIMESTAMPTZ,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    snippet               TEXT,
    body_text             TEXT,
    processing_status     TEXT NOT NULL DEFAULT 'new' CHECK (processing_status IN
        ('new','filtered','pending_llm','processed','manual_review','ignored','poison')),
    attempts              INT NOT NULL DEFAULT 0,
    next_attempt_at       TIMESTAMPTZ,
    error                 TEXT,
    event_type            TEXT,
    confidence            NUMERIC(4,3),
    extracted             JSONB,
    llm_model             TEXT,
    llm_prompt_tokens     INT,
    llm_completion_tokens INT,
    llm_cost_usd          NUMERIC(10,6),
    llm_attempts          INT,
    processed_at          TIMESTAMPTZ
);
CREATE INDEX email_log_queue_idx ON email_log (processing_status, next_attempt_at);
CREATE UNIQUE INDEX email_log_msgid_hdr_idx ON email_log (message_id_hdr)
    WHERE message_id_hdr IS NOT NULL;

-- ############ tracks ############
-- Путь магазин -> склад США. order_id NULL = непривязанный.
CREATE TABLE tracks (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tracking_number TEXT NOT NULL UNIQUE,          -- нормализованный: upper, без пробелов
    carrier         TEXT,
    order_id        BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    source          TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','email')),
    email_log_id    BIGINT REFERENCES email_log(id) ON DELETE SET NULL,
    match_status    TEXT NOT NULL DEFAULT 'linked'
        CHECK (match_status IN ('linked','open','dismissed')),
    candidates      JSONB,                         -- [{order_id, score, reasons, order_label}]
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX idx_tracks_order_id ON tracks (order_id);
CREATE INDEX idx_tracks_open ON tracks (created_at) WHERE match_status = 'open';

-- ############ payments ############
CREATE TABLE payments (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    paid_on    DATE NOT NULL DEFAULT CURRENT_DATE,
    amount_usd NUMERIC(12,2) NOT NULL CHECK (amount_usd > 0),
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_order_id ON payments (order_id);
CREATE INDEX idx_payments_paid_on ON payments (paid_on);

-- ############ order_status_history ############
CREATE TABLE order_status_history (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    old_status   TEXT,
    new_status   TEXT NOT NULL,
    source       TEXT NOT NULL CHECK (source IN ('auto','manual')),
    email_log_id BIGINT REFERENCES email_log(id) ON DELETE SET NULL,
    comment      TEXT,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_osh_order ON order_status_history (order_id, changed_at DESC);

-- ############ email_event ############
-- Лента действий автоматики для UI «Почта».
CREATE TABLE email_event (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email_id    BIGINT NOT NULL REFERENCES email_log(id) ON DELETE CASCADE,
    event_type  TEXT,
    order_id    BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    action      TEXT NOT NULL CHECK (action IN
        ('status_advanced','track_added','track_suggested','order_no_linked',
         'ignored_stale','ignored_terminal','manual_review','info')),
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_email_event_created ON email_event (created_at DESC);

-- ############ app_settings ############
CREATE TABLE app_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ############ gmail_credentials (singleton) ############
CREATE TABLE gmail_credentials (
    id                      SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    email_address           TEXT,
    refresh_token           TEXT NOT NULL,
    access_token            TEXT,
    access_token_expires_at TIMESTAMPTZ,
    authorized_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at              TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ############ gmail_sync_state (singleton) ############
CREATE TABLE gmail_sync_state (
    id                   SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    history_id           NUMERIC(20,0),
    last_poll_at         TIMESTAMPTZ,
    last_success_at      TIMESTAMPTZ,
    last_error           TEXT,
    consecutive_failures INT NOT NULL DEFAULT 0,
    llm_degraded         BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ############ seeds ############
INSERT INTO gmail_sync_state (id) VALUES (1);

INSERT INTO app_settings (key, value) VALUES
    ('llm.model',                  '"anthropic/claude-haiku-4.5"'),
    ('llm.enabled',                'true'),
    ('llm.max_http_attempts',      '3'),
    ('llm.max_validation_attempts','2'),
    ('mail.poll_interval_sec',     '180'),
    ('mail.backfill_days',         '30'),
    ('mail.whitelist_domains',     '["amazon.com","ebay.com","bestbuy.com","walmart.com","stockx.com","ups.com","usps.com","fedex.com","dhl.com"]'),
    ('mail.forwarder_domains',     '[]'),
    ('mail.gmail_query',           '""'),
    ('matching.auto_threshold',    '80'),
    ('matching.suggest_threshold', '40');
