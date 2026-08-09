"""Определение реального IP клиента за цепочкой прокси (haproxy → Caddy → backend).

Caddy (v2.7+) не доверяет X-Forwarded-For от клиента и пишет туда только
реальный адрес соединения, поэтому идём по заголовку справа налево и берём
первый публичный адрес. Приватный/непонятный адрес означает, что цепочка
прокси не передала реальный IP — такие адреса банить нельзя (это забанило бы
всех разом), для них остаётся мягкий глобальный лимит.
"""

from __future__ import annotations

import ipaddress

from fastapi import Request


def is_public_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def client_ip(request: Request) -> tuple[str, bool]:
    """(ip, bannable): публичный IP из X-Forwarded-For, иначе адрес сокета."""
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    for part in reversed(parts):
        if is_public_ip(part):
            return part, True
    host = request.client.host if request.client else ""
    return (host or "unknown"), is_public_ip(host)
