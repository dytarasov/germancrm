# shaprivezu

CRM для байера: выкуп товаров в интернет-магазинах США → склад-форвардер → рейс в Москву → клиент. Заказы привязаны к клиентам, статусы двигаются автоматически по письмам Gmail (разбор через LLM), деньги считаются сами. Отчётные периоды и «сегодня» считаются по московскому времени.

**Стек**: FastAPI + dishka + asyncpg (чистый SQL, без ORM) + PostgreSQL 16 · Next.js 15 + Tailwind v4 + TanStack Query · docker compose.

## Запуск одной кнопкой

Нужен Docker Desktop. Дальше:

```bash
make up          # соберёт и поднимет postgres + backend + frontend
```

Откройте http://localhost:3000, пароль — `APP_PASSWORD` из `.env` (файл создастся из `.env.example` при первом запуске — поменяйте пароль и `SECRET_KEY`).

Миграции применяются автоматически при старте бэкенда. Остановить: `make down`. Логи: `make logs`.

## Почта (Gmail) — включается позже, CRM работает и без неё

1. В [Google Cloud Console](https://console.cloud.google.com/) создайте проект → включите **Gmail API** (APIs & Services → Library).
2. **Важно:** на экране OAuth consent переведите приложение из Testing в **Production** (кнопка Publish app; верификацию проходить не нужно). В статусе Testing refresh token живёт всего 7 дней.
3. Credentials → Create credentials → OAuth client ID:
   - для прода — тип **Web application**, Authorized redirect URI: `https://shaprivezu.com/api/mail/oauth/callback` (точно совпадает с `PUBLIC_BASE_URL` + `/api/mail/oauth/callback`);
   - для локального запуска — тип **Desktop app** (redirect на localhost разрешён сам собой).
4. Впишите `GOOGLE_OAUTH_CLIENT_ID` и `GOOGLE_OAUTH_CLIENT_SECRET` в `.env`, примените: `docker compose up -d backend`.
5. В CRM: Настройки → «Подключить Gmail» **под аккаунтом рабочего ящика** → согласиться (экран «Google hasn’t verified this app» → Advanced → Continue).

Воркер читает только новые письма (whitelist доменов магазинов настраивается в Настройках), распознаёт их через LLM и двигает статусы: «магазин отправил» (появился трек) и «посылка на складе США». Всё остальное — руками; автоматика никогда не двигает статусы назад и не трогает отменённые/закрытые заказы. Нераспознанные письма попадают в очередь на экране «Почта».

## LLM (OpenRouter)

Впишите `OPENROUTER_API_KEY` в `.env` (ключ на [openrouter.ai](https://openrouter.ai/keys)). Модель выбирается в Настройках без рестарта (слаг OpenRouter, по умолчанию `anthropic/claude-haiku-4.5`); там же кнопка «Проверить». Стоимость ~пол-цента за письмо. Без ключа письма честно копятся в очереди «Ждут LLM» и обработаются, когда ключ появится.

## Бэкапы

Работают сами: сервис `backup` в compose делает `pg_dump` при старте и дальше раз в сутки, складывает в `./backups/crm-ГГГГММДД-ЧЧММСС.sql` и хранит последние 14 копий. Вручную в любой момент:

```bash
make backup      # pg_dump в ./backups/crm-ГГГГММДД-ЧЧММСС.sql
```

Восстановление: `cat backups/crm-... .sql | docker compose exec -T postgres psql -U crm crm`.

## Тесты

```bash
make test        # unit (без БД)
make test-int    # integration: поднимет временный Postgres на :5433, прогонит, погасит
```

## Прод (VPS + домен)

Прод развёрнут на https://shaprivezu.com (каталог `/opt/shaprivezu` на сервере). Схема: тот же compose + оверлей `docker-compose.prod.yml` с Caddy — он слушает 80/443 и сам получает/продлевает Let's Encrypt-сертификат; backend и frontend привязаны к loopback и наружу не торчат.

```bash
make up-prod     # docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

В `.env` на сервере обязательно: свои `APP_PASSWORD`, `SECRET_KEY`, `POSTGRES_PASSWORD` (с дефолтными приложение не стартует вне localhost), `COOKIE_SECURE=true`, `DOMAIN=shaprivezu.com`, `BACKEND_PORT=127.0.0.1:8000`, `FRONTEND_PORT=127.0.0.1:3000`, `PUBLIC_BASE_URL`/`FRONTEND_BASE_URL=https://shaprivezu.com`.

Заметки:
- Сервер маленький (1 ГБ RAM) — фронтенд там не собирается: образы `shaprivezu-backend`/`shaprivezu-frontend` собираются локально под `linux/amd64` и заливаются `docker save | ssh docker load`, на сервере `up -d --no-build`.
- Перенос данных: `make backup` → restore (refresh token Gmail переезжает вместе с БД, реавторизация не нужна). Все вызовы Gmail/OpenRouter — исходящие.

## Структура

```
backend/   FastAPI: src/crm/{domain,application,infrastructure,presentation,di}
           migrations/*.sql — применяются в lifespan (advisory lock + checksum)
frontend/  Next.js 15, экраны: дашборд, заказы, клиенты, треки, рейсы, деньги, почта, настройки
```

Правила домена, которые бережёт система: пустая комиссия ≠ 0; заказ не закрыть без комиссии; номер заказа и трек необязательны; статус всегда можно поправить руками, включая откат.
