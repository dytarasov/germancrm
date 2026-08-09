"""client_ip: реальный публичный адрес из X-Forwarded-For, справа налево.

Правая часть заголовка заполняется нашими прокси, левую может подделать клиент —
поэтому берём именно ПРАВЫЙ публичный адрес. Приватные адреса не bannable:
это страховка от самобана всех пользователей при сломанной цепочке прокси.
"""

from __future__ import annotations

from starlette.requests import Request

from crm.presentation.ip import client_ip, is_public_ip


def _request(xff: str | None, client_host: str = "127.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": headers,
            "client": (client_host, 1234),
            "query_string": b"",
        }
    )


class TestClientIp:
    def test_single_public_xff(self):
        assert client_ip(_request("5.6.7.8")) == ("5.6.7.8", True)

    def test_rightmost_public_wins_over_spoofed_left(self):
        # клиент прислал фальшивый левый хвост — берём правый публичный (наш прокси)
        assert client_ip(_request("8.8.8.8, 5.6.7.8")) == ("5.6.7.8", True)

    def test_private_tail_skipped(self):
        # справа адрес докер-сети (дописал внутренний прокси) — идём левее
        assert client_ip(_request("5.6.7.8, 172.18.0.5")) == ("5.6.7.8", True)

    def test_no_public_anywhere_falls_back_to_socket(self):
        ip, bannable = client_ip(_request("10.0.0.1, 172.18.0.5"))
        assert ip == "127.0.0.1"
        assert bannable is False

    def test_no_xff_private_socket_not_bannable(self):
        assert client_ip(_request(None)) == ("127.0.0.1", False)

    def test_no_xff_public_socket_bannable(self):
        assert client_ip(_request(None, client_host="1.2.3.4")) == ("1.2.3.4", True)

    def test_garbage_xff_ignored(self):
        assert client_ip(_request("not-an-ip, ,")) == ("127.0.0.1", False)


class TestIsPublicIp:
    def test_common_cases(self):
        assert is_public_ip("8.8.8.8") is True
        assert is_public_ip("178.17.57.20") is True
        assert is_public_ip("127.0.0.1") is False
        assert is_public_ip("10.1.2.3") is False
        assert is_public_ip("172.18.0.5") is False
        assert is_public_ip("192.168.1.1") is False
        # TEST-NET из документации ipaddress считает не-глобальным — тоже не баним
        assert is_public_ip("203.0.113.7") is False
        assert is_public_ip("") is False
        assert is_public_ip("mango") is False
