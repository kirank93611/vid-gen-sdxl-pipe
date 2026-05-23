"""API key authentication helpers for protected routes."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

import api_config

logger = logging.getLogger("sdxl_api")


def auth_error_response(request_id: str) -> JSONResponse:
    response = JSONResponse(
        status_code=401,
        content={
            "status": "error",
            "error_code": "unauthorized",
            "message": "Invalid or missing API key",
            "request_id": request_id,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


def require_api_key(http_request: Request) -> JSONResponse | None:
    """Return 401 response if key is missing or wrong; else None."""
    request_id = getattr(http_request.state, "request_id", "unknown")
    provided = http_request.headers.get(api_config.API_KEY_HEADER, "")
    if provided != api_config.EXPECTED_API_KEY:
        logger.error(
            "request rejected reason=invalid_api_key",
            extra={"request_id": request_id},
        )
        return auth_error_response(request_id)
    return None
