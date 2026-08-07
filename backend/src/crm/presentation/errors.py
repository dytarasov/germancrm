from __future__ import annotations

import logging

import asyncpg
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from crm.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    DomainError,
    DomainValidationError,
    NotFoundError,
)

log = logging.getLogger("crm.errors")

_STATUS_MAP: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (DomainValidationError, 422),
    (AuthenticationError, 401),
]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        status = 500
        for cls, code in _STATUS_MAP:
            if isinstance(exc, cls):
                status = code
                break
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": exc.code, "message": exc.message, "details": exc.details}
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # единый формат ошибок и для явных HTTPException (например, 429 на логине)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation",
                    "message": "Неверные данные запроса",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    @app.exception_handler(asyncpg.DataError)
    async def data_error_handler(request: Request, exc: asyncpg.DataError) -> JSONResponse:
        # Страховка для значений, не влезающих в колонку (NUMERIC(12,2), int и т.п.):
        # семантические нарушения (FK/NotNull/Unique) репозитории переводят сами,
        # а «число вне диапазона» может прилететь из любого INSERT/UPDATE.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "value_out_of_range",
                    "message": "Значение вне допустимого диапазона",
                    "details": {},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Необработанная ошибка: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "internal", "message": "Внутренняя ошибка сервера", "details": {}}
            },
        )
