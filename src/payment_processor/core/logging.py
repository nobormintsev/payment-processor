import json
import logging
import sys
from typing import Any

from payment_processor.core.enums import LogLevel

_STANDARD_LOG_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Безопасный JSON-форматтер логов."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Прикрепляем extra-поля (logger.info(..., extra={"key": value}))
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_ATTRS and not key.startswith("_"):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False, default=str)


def configure_logging(level: LogLevel, use_json: bool = False) -> None:
    if use_json:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logging.basicConfig(level=level.value, handlers=[handler], force=True)

    for noisy_logger in ("aio_pika", "aiormq", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
