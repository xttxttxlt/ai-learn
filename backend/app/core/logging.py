import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from app.core.config import BASE_DIR, get_settings

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "backend.log"


def _configure_windows_console() -> None:
    """Windows 控制台切到 UTF-8，避免中文日志乱码。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:  # noqa: BLE001
        pass


def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def _build_file_handler(level: int) -> RotatingFileHandler | None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler
    except OSError:
        return None


def setup_logging() -> None:
    _configure_windows_console()
    _force_utf8_streams()

    settings = get_settings()
    level = logging.getLevelName(settings.log_level.upper())
    if not isinstance(level, int):
        level = logging.INFO

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(message)s"))

    handlers: list[logging.Handler] = [console]
    file_handler = (
        None if settings.app_env == "test" else _build_file_handler(level)
    )
    if file_handler is not None:
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)

    if file_handler is not None:
        # uvicorn 使用独立 logger，默认不向 root 传播；挂到 uvicorn 与 access。
        for name in ("uvicorn", "uvicorn.access"):
            uvicorn_logger = logging.getLogger(name)
            if file_handler not in uvicorn_logger.handlers:
                uvicorn_logger.addHandler(file_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
