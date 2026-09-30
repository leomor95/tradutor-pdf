from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tradutor_pdf.config import find_project_root

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"


def setup_logging(
    log_dir: Path | str | None = None,
    log_level: int = logging.INFO,
    app_logger_name: str = "tradutor_pdf",
) -> logging.Logger:
    """Configure rotating file logging in logs/ and console output."""
    if log_dir is None:
        target_dir = find_project_root() / "logs"
    else:
        target_dir = Path(log_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "app.log"

    logger = logging.getLogger(app_logger_name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


class StageTimer:
    """Stores elapsed execution time for a pipeline stage."""

    def __init__(self, name: str, page: int | None = None) -> None:
        self.name = name
        self.page = page
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.elapsed: float = 0.0

    def start(self) -> None:
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        self.end_time = time.perf_counter()
        self.elapsed = self.end_time - self.start_time
        return self.elapsed


@contextmanager
def timed_stage(
    stage_name: str,
    page: int | None = None,
    logger: logging.Logger | None = None,
) -> Generator[StageTimer, None, None]:
    """Context manager to measure and log duration of a pipeline stage (RNF22)."""
    log = logger or logging.getLogger("tradutor_pdf")
    timer = StageTimer(name=stage_name, page=page)
    target_info = f"page {page}" if page is not None else ""
    info_suffix = f" ({target_info})" if target_info else ""

    log.info("Starting stage: %s%s", stage_name, info_suffix)
    timer.start()
    try:
        yield timer
    except Exception as exc:
        timer.stop()
        log.error(
            "Stage %s%s failed after %.2fs with error: %s",
            stage_name,
            info_suffix,
            timer.elapsed,
            exc,
        )
        raise
    else:
        timer.stop()
        log.info(
            "Finished stage: %s%s in %.2fs",
            stage_name,
            info_suffix,
            timer.elapsed,
        )
