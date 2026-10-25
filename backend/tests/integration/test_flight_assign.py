"""Распределение заказов по рейсу галками: POST /api/flights/{id}/orders."""

from __future__ import annotations


async def _order_at_warehouse(authed, client_id: int) -> int:
    resp = await authed.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "store": "eBay",
            "items": "Кроссовки",
            "purchase_price_usd": "100.00",
        },
    )
    assert resp.status_code == 201, resp.text
    oid = resp.json()["id"]
    resp = await authed.post(f"/api/orders/{oid}/status", json={"status": "at_warehouse"})
    assert resp.status_code == 200, resp.text
    return oid


async def test_assign_and_unassign(authed):
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    a = await _order_at_warehouse(authed, client_id)
    b = await _order_at_warehouse(authed, client_id)
    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-10", "cost_usd": "300"})
    ).json()

    # отметили оба — привязаны к рейсу и уехали «Рейсом», подзаказы тоже
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"add": [a, b]})
    assert resp.status_code == 200, resp.text
    assert sorted(o["id"] for o in resp.json()["orders"]) == [a, b]
    detail = (await authed.get(f"/api/orders/{a}")).json()
    assert detail["status"] == "in_flight"
    assert detail["flight_id"] == flight["id"]
    assert {s["status"] for s in detail["suborders"]} == {"in_flight"}
    assert detail["history"][0]["comment"] == "рейс от 10.10.2026"

    # сняли галку — отвязан и вернулся в «Получено в США»
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"remove": [b]})
    assert [o["id"] for o in resp.json()["orders"]] == [a]
    detail = (await authed.get(f"/api/orders/{b}")).json()
    assert detail["status"] == "at_warehouse"
    assert detail["flight_id"] is None


async def test_unassign_delivered_keeps_status_and_undo_relinks(authed):
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    oid = await _order_at_warehouse(authed, client_id)
    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-10", "cost_usd": "0"})
    ).json()
    url = f"/api/flights/{flight['id']}/orders"
    await authed.post(url, json={"add": [oid]})
    await authed.post(f"/api/orders/{oid}/status", json={"status": "delivered"})

    # снятие доставленного заказа не откатывает статус
    await authed.post(url, json={"remove": [oid]})
    detail = (await authed.get(f"/api/orders/{oid}")).json()
    assert (detail["status"], detail["flight_id"]) == ("delivered", None)

    # «Отменить» в тосте = обратная привязка; статус по-прежнему доставлен
    resp = await authed.post(url, json={"add": [oid]})
    assert resp.status_code == 200, resp.text
    detail = (await authed.get(f"/api/orders/{oid}")).json()
    assert (detail["status"], detail["flight_id"]) == ("delivered", flight["id"])


async def test_assign_from_purchased_goes_straight_to_flight(authed):
    """Письма о доставке на склад не было — галка переводит «Куплен» сразу в «Рейс»."""
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    resp = await authed.post(
        "/api/orders",
        json={"client_id": client_id, "store": "eBay", "items": "x", "purchase_price_usd": "1"},
    )
    oid = resp.json()["id"]  # purchased
    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-10", "cost_usd": "0"})
    ).json()
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"add": [oid]})
    assert resp.status_code == 200, resp.text
    detail = (await authed.get(f"/api/orders/{oid}")).json()
    assert (detail["status"], detail["flight_id"]) == ("in_flight", flight["id"])
    assert detail["history"][0]["old_status"] == "purchased"

    # сняли с рейса (или «Отменить» в тосте) — вернулся в «Куплен», а не в «Получено в США»
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"remove": [oid]})
    assert resp.status_code == 200, resp.text
    detail = (await authed.get(f"/api/orders/{oid}")).json()
    assert (detail["status"], detail["flight_id"]) == ("purchased", None)


async def test_assign_rejects_cancelled_order(authed):
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    ok = await _order_at_warehouse(authed, client_id)
    resp = await authed.post(
        "/api/orders",
        json={"client_id": client_id, "store": "eBay", "items": "x", "purchase_price_usd": "1"},
    )
    cancelled = resp.json()["id"]
    assert (await authed.post(f"/api/orders/{cancelled}/cancel")).status_code == 200
    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-10", "cost_usd": "0"})
    ).json()
    resp = await authed.post(
        f"/api/flights/{flight['id']}/orders", json={"add": [ok, cancelled]}
    )
    assert resp.status_code == 422
    # пакет атомарный: ничего не привязалось и статус не сменился
    detail = (await authed.get(f"/api/orders/{ok}")).json()
    assert (detail["status"], detail["flight_id"]) == ("at_warehouse", None)
    assert (await authed.get(f"/api/orders/{cancelled}")).json()["flight_id"] is None


async def test_assign_unknown_flight_is_404(authed):
    resp = await authed.post("/api/flights/999/orders", json={"add": [1]})
    assert resp.status_code == 404


async def test_in_flight_without_flight_is_listed_and_can_be_linked(authed):
    """«Рейс» поставили кликом из списка, рейс не выбрали: в списке это видно
    (flight_id = null), и галка на экране рейса привязывает без смены статуса."""
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    oid = await _order_at_warehouse(authed, client_id)
    resp = await authed.post(f"/api/orders/{oid}/status", json={"status": "in_flight"})
    assert resp.status_code == 200, resp.text

    rows = (await authed.get("/api/orders", params={"status": "in_flight"})).json()
    assert [(r["id"], r["flight_id"]) for r in rows] == [(oid, None)]

    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-20", "cost_usd": "100"})
    ).json()
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"add": [oid]})
    assert resp.status_code == 200, resp.text
    rows = (await authed.get("/api/orders", params={"status": "in_flight"})).json()
    assert [(r["id"], r["flight_id"]) for r in rows] == [(oid, flight["id"])]


async def test_unlink_manual_in_flight_keeps_status(authed):
    """«Рейс» поставили кликом вручную, потом привязали галкой и сняли (или «Отменить»):
    заказ остаётся в «Рейсе», просто без привязки — откатывать нечего."""
    client_id = (await authed.post("/api/clients", json={"name": "Тестов"})).json()["id"]
    oid = await _order_at_warehouse(authed, client_id)
    await authed.post(f"/api/orders/{oid}/status", json={"status": "in_flight"})
    flight = (
        await authed.post("/api/flights", json={"departed_on": "2026-10-20", "cost_usd": "100"})
    ).json()
    await authed.post(f"/api/flights/{flight['id']}/orders", json={"add": [oid]})
    resp = await authed.post(f"/api/flights/{flight['id']}/orders", json={"remove": [oid]})
    assert resp.status_code == 200, resp.text
    detail = (await authed.get(f"/api/orders/{oid}")).json()
    assert (detail["status"], detail["flight_id"]) == ("in_flight", None)
