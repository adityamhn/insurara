"""Uniform error envelope ({"error": {code, message}}) per SPEC §5.5."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..service.claims import ClaimError


class NotFound(HTTPException):
    def __init__(self, message: str):
        super().__init__(status_code=404, detail=message)


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ClaimError)
    async def _claim_error(_: Request, exc: ClaimError) -> JSONResponse:
        return _envelope(400, "invalid_claim", str(exc))

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", str(exc.errors()))
