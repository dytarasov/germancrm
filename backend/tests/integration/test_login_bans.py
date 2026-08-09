"""Регрессия на PgLoginBanRepository против живого Postgres: инкремент, порог,
окно сброса и снятие истёкшего бана. Логику окна/бана проверяем на реальном SQL
(now(), make_interval), а не на питоновской реплике."""

from __future__ import annotations

from crm.infrastructure.repositories.login_ban_repo import PgLoginBanRepository

IP = "203.0.113.9"
_ARGS = {"reset_window_min": 60, "max_fails": 5, "ban_hours": 48}


async def test_fifth_fail_triggers_ban(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        for i in range(1, 5):
            ban = await repo.register_fail(IP, **_ARGS)
            assert ban.fails == i
            assert ban.banned_until is None  # до порога бана нет
        ban = await repo.register_fail(IP, **_ARGS)  # пятый
        assert ban.fails == 5
        assert ban.banned_until is not None


async def test_sixth_fail_does_not_reset_or_reban(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        first = None
        for _ in range(5):
            first = await repo.register_fail(IP, **_ARGS)
        sixth = await repo.register_fail(IP, **_ARGS)
        assert sixth.fails == 6
        # banned_until не пересоздаётся на каждом промахе — держится исходный срок
        assert sixth.banned_until == first.banned_until


async def test_reset_window_restarts_counter(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        await repo.register_fail(IP, **_ARGS)
        await repo.register_fail(IP, **_ARGS)
        # последний промах «состарился» за окно сброса
        await conn.execute(
            "UPDATE login_bans SET last_fail_at = now() - interval '2 hours' WHERE ip = $1", IP
        )
        ban = await repo.register_fail(IP, **_ARGS)
        assert ban.fails == 1  # редкие промахи не накапливаются в бан


async def test_expired_ban_resets_before_counting(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        for _ in range(5):
            await repo.register_fail(IP, **_ARGS)
        # бан истёк
        await conn.execute(
            "UPDATE login_bans SET banned_until = now() - interval '1 hour' WHERE ip = $1", IP
        )
        ban = await repo.register_fail(IP, **_ARGS)
        # счётчик стартует заново, а не «дозакрывается» до 6 с мгновенным ре-баном
        assert ban.fails == 1
        assert ban.banned_until is None


async def test_clear_removes_row(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        await repo.register_fail(IP, **_ARGS)
        await repo.clear(IP)
        assert await repo.get(IP) is None


async def test_list_recent_keeps_active_ban_but_drops_stale(pool):
    async with pool.acquire() as conn:
        repo = PgLoginBanRepository(conn)
        for _ in range(5):
            await repo.register_fail(IP, **_ARGS)  # активный бан
        await repo.register_fail("198.51.100.7", **_ARGS)  # одиночный старый промах
        await conn.execute(
            "UPDATE login_bans SET last_fail_at = now() - interval '8 days' "
            "WHERE ip = '198.51.100.7'"
        )
        rows = await repo.list_recent()
        ips = {r.ip for r in rows}
        assert IP in ips  # активный бан не вычищается
        assert "198.51.100.7" not in ips  # давняя неактивная строка убрана
