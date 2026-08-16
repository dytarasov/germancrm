# Развернуть shaprivezu с нуля — пошагово

Инструкция для человека, который получил этот репозиторий и хочет поднять CRM на своём сервере. Ничего, кроме умения копировать команды в терминал, не требуется. По времени: около часа, из них минут двадцать — ожидание сборки.

Что получится в итоге: сайт `https://ваш-домен` с CRM, HTTPS-сертификат выпускается и продлевается сам, база бэкапится сама, обновления накатываются одной командой.

Что понадобится:

| Что | Зачем | Стоимость |
|---|---|---|
| VPS (арендованный сервер) | здесь всё работает | ~5 €/мес |
| Домен | адрес сайта и HTTPS | ~10–15 €/год |
| Аккаунт Google | почта Gmail, которую читает CRM + бэкапы на Google Drive | бесплатно |
| Ключ [openrouter.ai](https://openrouter.ai) | LLM, который разбирает письма | ~полцента за письмо |
| Доступ к этому репозиторию на GitHub | получать код и обновления | — |

Везде ниже замените `example.com` на свой домен, а `1.2.3.4` — на IP своего сервера.

---

## Шаг 1. Арендовать VPS

Подойдёт любой провайдер: Hetzner, DigitalOcean, Vultr; если платить из России — timeweb.cloud, aeza и подобные.

При заказе выберите:

- **ОС:** Ubuntu 24.04 LTS;
- **Ресурсы:** минимум 1 vCPU / 1 ГБ RAM / 20 ГБ диска — этого хватает (прод так и живёт), но первая сборка идёт минут 10–15. С 2 ГБ RAM будет комфортнее;
- **SSH-ключ:** если провайдер предлагает добавить — добавьте (см. ниже), это удобнее и безопаснее пароля.

Создать SSH-ключ на **своём** компьютере (Mac: Терминал, Windows: PowerShell):

```bash
ssh-keygen -t ed25519
# на все вопросы можно просто жать Enter
cat ~/.ssh/id_ed25519.pub   # это публичный ключ — его и вставляют в панель провайдера
```

После создания сервера у вас будет его **IP-адрес** (вида `1.2.3.4`). Зайдите на сервер:

```bash
ssh root@1.2.3.4
```

Если пускает — шаг готов.

## Шаг 2. Домен

1. Купите домен у любого регистратора (Namecheap, Porkbun; в России — reg.ru и т.п.).
2. В панели управления DNS создайте **A-запись**: имя `@`, значение — IP сервера `1.2.3.4`.
3. Подождите 10–30 минут и проверьте с своего компьютера:

```bash
ping example.com
# в ответе должен быть IP вашего сервера
```

Пока DNS не указывает на сервер, HTTPS-сертификат не выпустится — дождитесь, прежде чем идти к шагу 6.

## Шаг 3. Подготовить сервер

Все команды этого шага выполняются **на сервере** (вы зашли по `ssh root@1.2.3.4`). Можно вставлять блоками целиком.

Обновления и базовые пакеты:

```bash
apt update && apt -y upgrade
apt -y install git make curl
```

Docker (официальный установщик):

```bash
curl -fsSL https://get.docker.com | sh
```

Swap — обязательно, если RAM 1 ГБ (без него сборка фронтенда падает по памяти):

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Файрвол — наружу смотрят только SSH и веб:

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## Шаг 4. Получить код с GitHub

Репозиторий приватный, поэтому серверу нужен доступ. Самый простой путь — deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Скопируйте вывод последней команды (одна строка, начинается с `ssh-ed25519`) и отправьте владельцу репозитория — он добавит его в GitHub (Settings → Deploy keys → Add deploy key, галочку «write access» не ставить). Когда подтвердит — клонируйте:

```bash
git clone git@github.com:dytarasov/germancrm.git /opt/shaprivezu
cd /opt/shaprivezu
```

На вопрос про «authenticity of host github.com» ответьте `yes`.

## Шаг 5. Настроить переменные (.env)

Настройки живут в файле `/opt/shaprivezu/.env`. Его нет в git (там секреты) — создайте:

```bash
cd /opt/shaprivezu
nano .env
```

Вставьте шаблон и заполните три первых значения:

```ini
# === придумать/сгенерировать ===
APP_PASSWORD=придумайте-пароль-входа-в-CRM
SECRET_KEY=вставьте-результат-команды-ниже
POSTGRES_PASSWORD=вставьте-результат-команды-ниже

# === прод, поменять только домен ===
COOKIE_SECURE=true
DOMAIN=example.com
PUBLIC_BASE_URL=https://example.com
FRONTEND_BASE_URL=https://example.com
BACKEND_PORT=127.0.0.1:8000
FRONTEND_PORT=127.0.0.1:3000

# === заполняются на шаге 7, пока можно оставить пустыми ===
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
OPENROUTER_API_KEY=
```

Сгенерировать случайные строки для `SECRET_KEY` и `POSTGRES_PASSWORD` (запустите дважды, по одному разу на каждую):

```bash
openssl rand -hex 32
```

В nano: сохранить — `Ctrl+O`, Enter; выйти — `Ctrl+X`.

Пояснения к переменным:

| Переменная | Что это |
|---|---|
| `APP_PASSWORD` | пароль, которым вы входите в CRM через браузер |
| `SECRET_KEY` | подпись сессий; любая длинная случайная строка, никому не показывать |
| `POSTGRES_PASSWORD` | пароль базы данных. **Задаётся один раз до первого запуска** — потом просто так не поменять |
| `COOKIE_SECURE` | cookie только по HTTPS; на сервере всегда `true` |
| `DOMAIN` | домен — по нему Caddy выпускает HTTPS-сертификат |
| `PUBLIC_BASE_URL` / `FRONTEND_BASE_URL` | адрес сайта; участвует в подключении Gmail |
| `BACKEND_PORT` / `FRONTEND_PORT` | с `127.0.0.1:` внутренние сервисы не торчат в интернет — наружу только Caddy |
| `GOOGLE_OAUTH_*` | доступ к Gmail API — шаг 7 |
| `OPENROUTER_API_KEY` | ключ LLM — шаг 7 |

С дефолтными паролями приложение на прод-адресе нарочно **не стартует** — это защита от «забыл поменять».

## Шаг 6. Первый запуск

```bash
cd /opt/shaprivezu
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Первая сборка на маленьком сервере — 10–20 минут (дальше будет в разы быстрее, пересобирается только изменившееся). Когда команда завершится, проверьте:

```bash
docker compose ps        # у всех сервисов статус Up
curl http://127.0.0.1:8000/healthz   # должно ответить {"status":"ok"}
```

Откройте `https://example.com` в браузере — увидите экран входа, пароль — ваш `APP_PASSWORD`. Первую минуту-две после старта Caddy получает сертификат; если браузер ругается — подождите и обновите страницу.

CRM уже полностью рабочая: клиенты, заказы, рейсы, деньги. Автоматика писем включается следующим шагом.

## Шаг 7. Подключить Gmail и LLM

### Gmail (письма магазинов двигают статусы сами)

1. Зайдите в [Google Cloud Console](https://console.cloud.google.com/) под аккаунтом рабочего ящика → создайте проект.
2. APIs & Services → Library → включите **Gmail API** и **Google Drive API** (Drive нужен для оффсайт-бэкапов).
3. APIs & Services → OAuth consent screen: заполните минимум и нажмите **Publish app** (переведите из Testing в Production; проходить верификацию не нужно). В статусе Testing токен умирает каждые 7 дней — не пропускайте этот пункт.
4. Credentials → Create credentials → **OAuth client ID** → тип **Web application** → в Authorized redirect URIs добавьте ровно:
   ```
   https://example.com/api/mail/oauth/callback
   ```
5. Полученные Client ID и Client secret впишите в `.env` (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`) и примените:
   ```bash
   cd /opt/shaprivezu && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
6. В CRM: Настройки → «Подключить Gmail» → войдите **рабочим ящиком** → на предупреждении «Google hasn’t verified this app» нажмите Advanced → Continue.

### LLM (OpenRouter)

1. На [openrouter.ai/keys](https://openrouter.ai/keys) создайте ключ, пополните баланс (5 $ хватает очень надолго — письмо стоит около половины цента).
2. Впишите ключ в `.env` → `OPENROUTER_API_KEY` и повторите команду `up -d backend` из пункта выше.
3. В CRM: Настройки → кнопка «Проверить» рядом с моделью должна ответить успехом.

Без ключа ничего не ломается: письма честно копятся в очереди «Ждут LLM» и обработаются, когда ключ появится.

## Шаг 8. Обновления

Когда в репозиторий приходят правки, накатить их — одна и та же команда (можно сохранить себе):

```bash
cd /opt/shaprivezu && git pull --ff-only && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Пересоберётся и перезапустится только то, что изменилось; база и настройки не трогаются, миграции базы применяются сами при старте. Сайт недоступен секунд десять в момент перезапуска.

Правила, чтобы обновления всегда проходили гладко:

- **не редактируйте файлы проекта на сервере** — только `.env` (он не в git и обновлениям не мешает). Если отредактировать что-то ещё, `git pull` откажется работать; лечится `git checkout -- имя-файла` (вернёт файл к версии из git);
- не используйте `docker compose restart` — правильная команда всегда `up -d`.

## Шаг 9. Бэкапы

Работают сами, настраивать нечего:

- **на сервере**: дамп базы при каждом старте и дальше раз в сутки → `/opt/shaprivezu/backups/`, хранятся последние 14;
- **на Google Drive**: раз в сутки свежий дамп улетает в папку `shaprivezu-backups` на Drive подключённого ящика, хранится 60 копий — переживёт даже смерть сервера.

Сделать дамп руками: `cd /opt/shaprivezu && make backup`.

Восстановить базу из дампа (осторожно, перезапишет текущие данные):

```bash
cd /opt/shaprivezu
cat backups/crm-ГГГГММДД-ЧЧММСС.sql | docker compose exec -T postgres psql -U crm crm
```

При переезде на новый сервер: пройти шаги 1–6, затем залить последний дамп этой командой — Gmail переподключать не нужно, токен хранится в базе и переезжает вместе с ней.

## Если что-то сломалось

Первое действие всегда одно — посмотреть логи:

```bash
cd /opt/shaprivezu
docker compose logs --tail=100 backend    # логика, почта, LLM
docker compose logs --tail=100 caddy      # HTTPS, сертификаты
docker compose logs --tail=100 frontend   # интерфейс
```

Типовые ситуации:

| Симптом | Что делать |
|---|---|
| Сайт не открывается сразу после установки | Проверьте `ping example.com` → IP сервера; смотрите логи caddy — обычно это DNS ещё не доехал, сертификат выпустится сам |
| Сборка оборвалась, в логах `Killed` | Кончилась память: проверьте swap `free -h` (строка Swap не нулевая?) — шаг 3 |
| Забыли пароль CRM | `nano .env` → новый `APP_PASSWORD` → `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend` |
| Забанили себя неверными паролями | `docker compose exec postgres psql -U crm crm -c "DELETE FROM login_bans"` |
| Кончается диск | `df -h` посмотреть; `docker image prune -f` удалит старые образы от прошлых сборок (безопасно, данные не трогает) |
| Письма не обрабатываются | Экран «Почта» в CRM покажет очередь и причину; логи backend — детали |
| После перезагрузки сервера | Ничего делать не нужно — контейнеры поднимаются сами (`restart: unless-stopped`) |

## Шпаргалка

```bash
cd /opt/shaprivezu

# обновить до свежей версии
git pull --ff-only && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# статус / логи
docker compose ps
docker compose logs -f --tail=100 backend

# бэкап руками
make backup

# перечитать .env (после правок)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
```
