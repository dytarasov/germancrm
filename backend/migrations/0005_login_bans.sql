-- Защита входа: счётчик неверных паролей по IP и бан на 48 часов.
-- Строки живут недолго: успешный вход стирает свою, устаревшие чистятся при чтении списка.
CREATE TABLE login_bans (
    ip           TEXT PRIMARY KEY,
    fails        INT NOT NULL DEFAULT 0,
    last_fail_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    banned_until TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
