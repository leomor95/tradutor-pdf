from __future__ import annotations

from tradutor_pdf.config import load_settings
from tradutor_pdf.logging_setup import setup_logging
from tradutor_pdf.translation.ollama_client import OllamaClient


def main() -> None:
    """Application entrypoint for tradutor-pdf."""
    logger = setup_logging()
    settings = load_settings()

    logger.info(
        "Initializing Tradutor PDF (target: %s)", settings.translation.target_language
    )

    client = OllamaClient(
        host=settings.ollama_host,
        default_model=settings.translation.model,
    )
    device = client.detect_device(log_result=True)
    logger.info("Ready for processing on %s.", device)
