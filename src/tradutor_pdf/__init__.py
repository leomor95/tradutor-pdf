import os
from pathlib import Path

# Ensure isolated cache and model directories (RNF24)
_root_dir = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("XDG_CACHE_HOME", str(_root_dir / ".cache"))
os.environ.setdefault("HF_HOME", str(_root_dir / ".cache" / "hf"))
os.environ.setdefault("UV_CACHE_DIR", str(_root_dir / ".cache" / "uv"))
os.environ.setdefault("OLLAMA_MODELS", str(_root_dir / "models"))
os.environ.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

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
