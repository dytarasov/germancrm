"""Подзаказы против живого API/Postgres: создание корзиной, агрегатный статус,
жёсткий поиск по номеру (SQL-нормализация обязана совпадать с Python)."""

from __future__ import annotations

from crm.application.services.matching import normalize_number
from crm.infrastructure.repositories.suborder_repo import PgSuborderRepository


async def _make_order(authed, *, suborders=None, **overrides):
    resp = await authed.post("/api/clients", json={"name": "Тестов"})
    client_id = resp.json()["id"]
    payload = {
        "client_id": client_id,
        "store": "eBay",
        "items": "Карточки, 10 лотов",
        "purchase_price_usd": "500.00",
        **overrides,
    }
    if suborders is not None:
        payload["suborders"] = suborders
    resp = await authed.post("/api/orders", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_with_multiple_suborders(authed):
    order = await _make_order(
        authed,
        suborders=[
            {"store_order_number": "12-06132-55561", "amount_usd": "125.00"},
            {"store_order_number": "12-06132-55562", "amount_usd": "200.00"},
            {"store_order_number": "12-06132-55563", "amount_usd": "175.00"},
        ],
    )
    assert order["suborders_count"] == 3
    assert order["store_order_number"] == "12-06132-55561"  # первый номер — в строку списка
    assert [s["status"] for s in order["suborders"]] == ["purchased"] * 3

    # строка списка несёт количество подзаказов
    resp = await authed.get("/api/orders")
    row = next(o for o in resp.json() if o["id"] == order["id"])
    assert row["suborders_count"] == 3


async def test_create_without_suborders_gets_single_empty(authed):
    order = await _make_order(authed)
    assert order["suborders_count"] == 1
    assert order["suborders"][0]["store_order_number"] is None


async def test_aggregate_status_is_worst_of_suborders(authed):
    order = await _make_order(
        authed,
        suborders=[{"store_order_number": "A-1"}, {"store_order_number": "A-2"}],
    )
    oid = order["id"]
    subs = order["suborders"]

    # один подзаказ уехал вперёд — агрегат остаётся по отстающему
    resp = await authed.post(
        f"/api/orders/{oid}/suborders/{subs[0]['id']}/status", json={"status": "shipped"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "purchased"

    # догнал второй — агрегат подтянулся
    resp = await authed.post(
        f"/api/orders/{oid}/suborders/{subs[1]['id']}/status", json={"status": "shipped"}
    )
    assert resp.json()["status"] == "shipped"

    # отмена одного подзаказа не мешает остальным
    resp = await authed.post(
        f"/api/orders/{oid}/suborders/{subs[0]['id']}/status", json={"status": "cancelled"}
    )
    assert resp.json()["status"] == "shipped"

    # история смен уровня подзаказа помечена его id
    resp = await authed.get(f"/api/orders/{oid}/status-history")
    sub_entries = [h for h in resp.json() if h["suborder_id"] is not None]
    assert len(sub_entries) == 3


async def test_cannot_delete_last_suborder(authed):
    order = await _make_order(authed)
    oid = order["id"]
    sid = order["suborders"][0]["id"]
    resp = await authed.delete(f"/api/orders/{oid}/suborders/{sid}")
    assert resp.status_code == 422  # DomainValidationError

    # добавили второй — первый удалять можно
    resp = await authed.post(f"/api/orders/{oid}/suborders", json={"store_order_number": "B-2"})
    assert resp.status_code == 201
    resp = await authed.delete(f"/api/orders/{oid}/suborders/{sid}")
    assert resp.status_code == 204


async def test_terminal_order_suborders_are_frozen(authed):
    """У отменённого заказа состав подзаказов не правится: иначе добавление
    подзаказа молча воскресило бы заказ через агрегатный статус."""
    order = await _make_order(
        authed,
        suborders=[{"store_order_number": "C-1"}, {"store_order_number": "C-2"}],
        commission_usd="10.00",
    )
    oid = order["id"]
    sid = order["suborders"][0]["id"]

    resp = await authed.post(f"/api/orders/{oid}/cancel")
    assert resp.json()["status"] == "cancelled"
    # все подзаказы ушли в cancelled вместе с заказом
    assert {s["status"] for s in resp.json()["suborders"]} == {"cancelled"}

    for call in (
        authed.post(f"/api/orders/{oid}/suborders", json={"store_order_number": "C-3"}),
        authed.patch(f"/api/orders/{oid}/suborders/{sid}", json={"amount_usd": "5.00"}),
        authed.delete(f"/api/orders/{oid}/suborders/{sid}"),
        authed.post(f"/api/orders/{oid}/suborders/{sid}/status", json={"status": "shipped"}),
    ):
        assert (await call).status_code == 422

    assert (await authed.get(f"/api/orders/{oid}")).json()["status"] == "cancelled"

    # «Вернуть в работу» — штатный путь, он пишет историю
    resp = await authed.post(f"/api/orders/{oid}/status", json={"status": "purchased"})
    assert resp.json()["status"] == "purchased"
    assert {s["status"] for s in resp.json()["suborders"]} == {"purchased"}
    resp = await authed.post(f"/api/orders/{oid}/suborders", json={"store_order_number": "C-3"})
    assert resp.status_code == 201


async def test_find_by_number_normalization_matches_python(authed, pool):
    """SQL-нормализация в find_by_number обязана совпадать с normalize_number."""
    order = await _make_order(
        authed, suborders=[{"store_order_number": "12-06132 55561"}]
    )
    raw_variants = [
        "12-06132-55561",
        "12 06132 55561",
        "120613255561",
        "12-06132 55561",
        "‫12-06132-55561",  # невидимый RTL-символ из буфера обмена
    ]
    async with pool.acquire() as conn:
        repo = PgSuborderRepository(conn)
        for raw in raw_variants:
            hits = await repo.find_by_number(normalize_number(raw))
            assert [h.order_id for h in hits] == [order["id"]], raw


async def test_reassigning_track_resets_suborder(authed):
    """Перевешенный на другой заказ трек не должен тащить за собой подзаказ
    прежнего — иначе письма по нему двигали бы чужой заказ."""
    a = await _make_order(authed, suborders=[{"store_order_number": "A-1"}])
    b = await _make_order(authed, suborders=[{"store_order_number": "B-1"}])

    resp = await authed.post(
        f"/api/orders/{a['id']}/tracks", json={"tracking_number": "1Z999AA10123456784"}
    )
    assert resp.status_code == 201
    track = resp.json()
    assert track["suborder_id"] == a["suborders"][0]["id"]  # единственный активный

    resp = await authed.post(f"/api/tracks/{track['id']}/assign", json={"order_id": b["id"]})
    assert resp.status_code == 200
    assert resp.json()["order_id"] == b["id"]
    assert resp.json()["suborder_id"] == b["suborders"][0]["id"]  # подзаказ пересчитан

    # отвязка обнуляет и подзаказ
    resp = await authed.post(f"/api/tracks/{track['id']}/assign", json={"order_id": None})
    assert resp.json()["suborder_id"] is None

    # у заказа с несколькими активными подзаказами угадывать нечего
    resp = await authed.post(f"/api/orders/{b['id']}/suborders", json={"store_order_number": "B-2"})
    assert resp.status_code == 201
    resp = await authed.post(f"/api/tracks/{track['id']}/assign", json={"order_id": b["id"]})
    assert resp.json()["suborder_id"] is None


async def test_search_finds_order_by_suborder_number(authed):
    await _make_order(authed, suborders=[{"store_order_number": "ZX-777-42"}])
    resp = await authed.get("/api/orders", params={"search": "zx-777"})
    assert len(resp.json()) == 1
