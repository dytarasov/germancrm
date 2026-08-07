from __future__ import annotations

import asyncpg
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

router = APIRouter(tags=["health"], route_class=DishkaRoute)


@router.get("/healthz")
async def healthz(conn: FromDishka[asyncpg.Connection]) -> dict:
    await conn.fetchval("SELECT 1")
    return {"status": "ok"}
