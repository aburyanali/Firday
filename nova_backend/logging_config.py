import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import config


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "nova_backend.log"


class TraceIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(config.log_level.upper())

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s trace_id=%(trace_id)s %(message)s"
    )
    trace_filter = TraceIdFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(trace_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2_000_000,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(trace_filter)

    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)


class TraceLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("trace_id", self.extra.get("trace_id", "-"))
        return msg, kwargs


def get_logger(name: str, trace_id: str = "-") -> TraceLoggerAdapter:
    return TraceLoggerAdapter(logging.getLogger(name), {"trace_id": trace_id})
