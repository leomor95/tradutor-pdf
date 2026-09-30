import time
from pathlib import Path

import pytest

from tradutor_pdf.logging_setup import setup_logging, timed_stage


def test_setup_logging_creates_file(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir=log_dir, app_logger_name="test_logger_1")
    logger.info("Test message for isolated log")

    log_file = log_dir / "app.log"
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "Test message for isolated log" in content


def test_timed_stage_measures_elapsed(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir=log_dir, app_logger_name="test_logger_2")

    with timed_stage("test_stage", page=1, logger=logger) as timer:
        time.sleep(0.05)

    assert timer.elapsed >= 0.04
    log_file = log_dir / "app.log"
    content = log_file.read_text(encoding="utf-8")
    assert "Starting stage: test_stage (page 1)" in content
    assert "Finished stage: test_stage (page 1)" in content


def test_timed_stage_handles_exception(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir=log_dir, app_logger_name="test_logger_3")

    with (
        pytest.raises(ValueError, match="intentional error"),
        timed_stage("failing_stage", logger=logger) as timer,
    ):
        time.sleep(0.01)
        raise ValueError("intentional error")

    assert timer.elapsed >= 0.005
    log_file = log_dir / "app.log"
    content = log_file.read_text(encoding="utf-8")
    assert "failed after" in content
    assert "intentional error" in content
