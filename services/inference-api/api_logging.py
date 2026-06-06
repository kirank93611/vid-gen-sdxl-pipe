"""Request-scoped logging helpers."""

from __future__ import annotations

import logging


class RequestIdFilter(logging.Filter):
    """Ensure %(request_id)s exists on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("sdxl_api")
    if logger.handlers:
        return logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
    return logger


def log_info(logger: logging.Logger, message: str, request_id: str) -> None:
    logger.info(message, extra={"request_id": request_id})


def log_error(logger: logging.Logger, message: str, request_id: str) -> None:
    logger.error(message, extra={"request_id": request_id})
