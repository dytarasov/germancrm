from __future__ import annotations

from datetime import timedelta

from crm.domain.clock import business_today

# Даты в тестах — по бизнес-календарю (Москва), как и в SQL репозиториев.
TODAY = business_today()


async def test_unauthorized_401(api):
    resp = await api.get("/api/orders")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_wrong_password(api):
    resp = await api.post("/api/auth/login", json={"password": "nope"})
    assert resp.status_code == 401


async def test_login_rate_limit(api):
    for _ in range(10):
        resp = await api.post("/api/auth/login", json={"password": "nope"})
        assert resp.status_code == 401
    resp = await api.post("/api/auth/login", json={"password": "nope"})
    assert resp.status_code == 429
    assert "попыток" in resp.json()["error"]["message"]
    # верный пароль тоже заблокирован до конца окна — защита от перебора
    resp = await api.post("/api/auth/login", json={"password": "test-pass"})
    assert resp.status_code == 429


async def test_healthz_open(api):
    resp = await api.get("/healthz")
    assert resp.status_code == 200


async def test_login_ban_after_5_fails_from_one_ip(api):
    evil = {"X-Forwarded-For": "5.6.7.8"}
    for _ in range(4):
        resp = await api.post("/api/auth/login", json={"password": "nope"}, headers=evil)
        assert resp.status_code == 401
    # пятый промах — бан на 48 часов
    resp = await api.post("/api/auth/login", json={"password": "nope"}, headers=evil)
    assert resp.status_code == 429
    assert "заблокирован" in resp.json()["error"]["message"]
    # даже верный пароль с забаненного IP не пускаем
    resp = await api.post("/api/auth/login", json={"password": "test-pass"}, headers=evil)
    assert resp.status_code == 429
    # другой IP живёт своей жизнью
    resp = await api.post(
        "/api/auth/login",
        json={"password": "test-pass"},
        headers={"X-Forwarded-For": "8.8.4.4"},
    )
    assert resp.status_code == 204


async def test_ban_listed_and_removable_in_crm(api):
    evil = {"X-Forwarded-For": "5.6.7.8"}
    for _ in range(5):
        await api.post("/api/auth/login", json={"password": "nope"}, headers=evil)
    # владелец заходит со своего IP и видит атаку
    resp = await api.post("/api/auth/login", json={"password": "test-pass"})
    assert resp.status_code == 204
    resp = await api.get("/api/security/bans")
    assert resp.status_code == 200
    bans = resp.json()
    row = next(b for b in bans if b["ip"] == "5.6.7.8")
    assert row["fails"] == 5
    assert row["banned_until"] is not None
    # снимает бан — IP снова может логиниться
    resp = await api.delete("/api/security/bans/5.6.7.8")
    assert resp.status_code == 204
    resp = await api.post("/api/auth/login", json={"password": "test-pass"}, headers=evil)
    assert resp.status_code == 204


async def test_successful_login_resets_fail_counter(api):
    ip = {"X-Forwarded-For": "5.6.7.8"}
    for _ in range(4):
        await api.post("/api/auth/login", json={"password": "nope"}, headers=ip)
    resp = await api.post("/api/auth/login", json={"password": "test-pass"}, headers=ip)
    assert resp.status_code == 204
    # счётчик стёрт: новые 4 промаха — ещё не бан
    for _ in range(4):
        resp = await api.post("/api/auth/login", json={"password": "nope"}, headers=ip)
    assert resp.status_code == 401


async def test_docs_closed_without_auth(api):
    assert (await api.get("/api/openapi.json")).status_code == 401
    assert (await api.get("/api/docs")).status_code == 401


async def test_openapi_schema_generates(authed):
    """Регрессия: аннотация RedirectResponse в oauth_callback роняла генерацию схемы."""
    resp = await authed.get("/api/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "shaprivezu"


async def test_full_order_lifecycle(authed):
    # клиент
    resp = await authed.post(
        "/api/clients", json={"name": "Петров", "telegram_url": "https://t.me/petrov"}
    )
    assert resp.status_code == 201, resp.text
    client_id = resp.json()["id"]

    # заказ в момент покупки — минимум полей
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "Amazon",
            "items": "iPhone 17 Pro 256GB",
            "purchase_price_usd": "1050.00",
            "promised_date": str(TODAY + timedelta(days=21)),
        },
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    order_id = order["id"]
    assert order["status"] == "purchased"
    assert order["commission_usd"] is None
    assert order["due_usd"] is None  # комиссия не задана — остаток не определён

    # трек
    resp = await authed.post(
        f"/api/orders/{order_id}/tracks",
        json={"tracking_number": "1z 999 aa1 0123 456 784", "carrier": "ups"},
    )
    assert resp.status_code == 201
    assert resp.json()["tracking_number"] == "1Z999AA10123456784"

    # статусы вперёд по степперу
    for status in ("shipped", "at_warehouse", "in_flight", "delivered"):
        resp = await authed.post(f"/api/orders/{order_id}/status", json={"status": status})
        assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "delivered"

    # платежи частями
    for amount in ("500.00", "300.00"):
        resp = await authed.post(
            f"/api/orders/{order_id}/payments", json={"amount_usd": amount}
        )
        assert resp.status_code == 201

    # закрыть без комиссии нельзя — 409 с точным кодом
    resp = await authed.post(f"/api/orders/{order_id}/close")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "commission_required"

    # вес + комиссия (веc*50 подсказывает фронт, поле одно)
    resp = await authed.patch(
        f"/api/orders/{order_id}", json={"weight_kg": "2.4", "commission_usd": "120.00"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["finance"]["revenue_usd"] == "1170.00"
    assert body["finance"]["paid_usd"] == "800.00"
    assert body["finance"]["due_usd"] == "370.00"

    resp = await authed.post(f"/api/orders/{order_id}/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
    assert resp.json()["closed_at"] is not None

    # история: purchased -> ... -> closed, все manual
    resp = await authed.get(f"/api/orders/{order_id}/status-history")
    history = resp.json()
    assert history[0]["new_status"] == "closed"
    assert all(h["source"] == "manual" for h in history)

    # дашборд видит прибыль месяца
    resp = await authed.get("/api/dashboard")
    dash = resp.json()
    assert dash["month_commissions_usd"] == "120.00"
    assert dash["orders_in_progress"] == 0

    # отчёт за месяц
    resp = await authed.get(
        "/api/reports/money",
        params={"from": str(TODAY.replace(day=1)), "to": str(TODAY)},
    )
    report = resp.json()
    assert report["commissions_usd"] == "120.00"
    assert len(report["orders"]) == 1


async def test_copy_and_cancel(authed):
    resp = await authed.post("/api/clients", json={"name": "Сидоров"})
    client_id = resp.json()["id"]
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "StockX",
            "items": "Кроссовки",
            "purchase_price_usd": "250.00",
            "commission_usd": "60.00",
            "store_order_number": "SX-1001",
        },
    )
    order_id = resp.json()["id"]

    resp = await authed.post(f"/api/orders/{order_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = await authed.post(f"/api/orders/{order_id}/copy")
    assert resp.status_code == 201
    copy = resp.json()
    assert copy["copied_from"] == order_id
    assert copy["status"] == "purchased"
    assert copy["store_order_number"] is None
    assert copy["commission_usd"] == "60.00"

    # отменённый ушёл из активных, но остался в истории
    resp = await authed.get("/api/orders", params={"active": "true"})
    active_ids = [o["id"] for o in resp.json()]
    assert copy["id"] in active_ids and order_id not in active_ids
    resp = await authed.get("/api/orders")
    assert order_id in [o["id"] for o in resp.json()]


async def test_refund_flow(authed):
    resp = await authed.post("/api/clients", json={"name": "Кузнецов"})
    client_id = resp.json()["id"]
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "BestBuy",
            "items": "Наушники",
            "purchase_price_usd": "300.00",
            "commission_usd": "80.00",
        },
    )
    order_id = resp.json()["id"]
    resp = await authed.post(
        f"/api/orders/{order_id}/refund",
        json={"refunded_amount_usd": "300.00", "commission_usd": "0.00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "refunded"
    assert body["refunded_amount_usd"] == "300.00"
    assert body["commission_usd"] == "0.00"


async def test_unmatched_tracks_and_assign(authed):
    resp = await authed.post("/api/clients", json={"name": "Фёдоров"})
    client_id = resp.json()["id"]
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "Amazon",
            "items": "Запчасти",
            "purchase_price_usd": "150.00",
        },
    )
    order_id = resp.json()["id"]

    # «пришёл трек, чей — непонятно»
    resp = await authed.post("/api/tracks", json={"tracking_number": "9400111899223197428490"})
    assert resp.status_code == 201
    track = resp.json()
    assert track["order_id"] is None
    assert track["match_status"] == "open"

    resp = await authed.get("/api/tracks", params={"unmatched": "true"})
    assert len(resp.json()) == 1

    resp = await authed.get(f"/api/tracks/{track['id']}/suggestions")
    assert resp.status_code == 200
    suggestions = resp.json()
    assert suggestions and suggestions[0]["order_id"] == order_id

    resp = await authed.post(f"/api/tracks/{track['id']}/assign", json={"order_id": order_id})
    assert resp.json()["match_status"] == "linked"
    resp = await authed.get("/api/tracks", params={"unmatched": "true"})
    assert resp.json() == []


async def test_order_items_lifecycle(authed):
    resp = await authed.post("/api/clients", json={"name": "Орлов"})
    client_id = resp.json()["id"]

    # заказ сразу со ссылками — каждая становится позицией
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "Amazon",
            "items": "Телефон + аксессуары",
            "purchase_price_usd": "1200.00",
            "links": ["https://amazon.com/dp/B0AAA", "https://amazon.com/dp/B0BBB"],
        },
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    order_id = order["id"]
    assert [i["url"] for i in order["order_items"]] == [
        "https://amazon.com/dp/B0AAA",
        "https://amazon.com/dp/B0BBB",
    ]

    # добавить позицию с названием и количеством
    resp = await authed.post(
        f"/api/orders/{order_id}/items",
        json={"title": "Чехол MagSafe", "quantity": 2},
    )
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    # пустая позиция запрещена
    resp = await authed.post(f"/api/orders/{order_id}/items", json={})
    assert resp.status_code == 422

    resp = await authed.patch(
        f"/api/orders/{order_id}/items/{item_id}", json={"quantity": 3}
    )
    assert resp.json()["quantity"] == 3

    # поиск находит заказ по названию позиции
    resp = await authed.get("/api/orders", params={"search": "magsafe"})
    assert [o["id"] for o in resp.json()] == [order_id]

    # копия забирает позиции с собой
    resp = await authed.post(f"/api/orders/{order_id}/copy")
    copy = resp.json()
    assert len(copy["order_items"]) == 3

    resp = await authed.delete(f"/api/orders/{order_id}/items/{item_id}")
    assert resp.status_code == 204
    resp = await authed.get(f"/api/orders/{order_id}")
    assert len(resp.json()["order_items"]) == 2


async def test_numeric_overflow_is_422(authed):
    """Регрессия: цена, не влезающая в NUMERIC(12,2), давала 500 вместо 422."""
    resp = await authed.post("/api/clients", json={"name": "Богатов"})
    client_id = resp.json()["id"]
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "Amazon",
            "items": "Слишком дорого",
            "purchase_price_usd": "99999999999.99",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "value_out_of_range"

    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "Amazon",
            "items": "Ок",
            "purchase_price_usd": "10.00",
        },
    )
    order_id = resp.json()["id"]
    resp = await authed.post(
        f"/api/orders/{order_id}/payments", json={"amount_usd": "99999999999.99"}
    )
    assert resp.status_code == 422


async def test_client_delete_conflict(authed):
    resp = await authed.post("/api/clients", json={"name": "Смирнов"})
    client_id = resp.json()["id"]
    await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "eBay",
            "items": "Часы",
            "purchase_price_usd": "80.00",
        },
    )
    resp = await authed.delete(f"/api/clients/{client_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "entity_in_use"


async def test_settings_view_and_patch(authed):
    resp = await authed.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_model"]
    assert body["gmail"]["connected"] is False

    resp = await authed.patch(
        "/api/settings",
        json={"llm_model": "openai/gpt-5-mini", "whitelist_domains": ["amazon.com", "b-h.com"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_model"] == "openai/gpt-5-mini"
    assert "b-h.com" in body["whitelist_domains"]


async def test_mail_health_without_setup(authed):
    resp = await authed.get("/api/mail/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gmail_connected"] is False
    assert body["configured"] is False
