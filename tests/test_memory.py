from __future__ import annotations

import gc
import logging
import subprocess
import time
from pathlib import Path

import psutil
import pytest

from scripts.gen_big_pdf import generate_synthetic_pdf
from tradutor_pdf import run_cli
from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.pipeline import Chunk, Translator

logger = logging.getLogger(__name__)


def get_current_rss_gb() -> float:
    """Return the current resident set size (RSS) in gigabytes for this process."""
    proc = psutil.Process()
    return proc.memory_info().rss / (1024**3)


def get_gpu_vram_gb() -> float:
    """Return currently allocated VRAM across NVIDIA GPUs in gigabytes, or 0.0 if not available."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        lines = out.strip().split("\n")
        if lines and lines[0]:
            used_mb = float(lines[0].strip())
            return used_mb / 1024.0
    except Exception as exc:  # noqa: BLE001
        logger.debug("nvidia-smi query failed: %s", exc)
    return 0.0


class MemoryTrackTranslator(Translator):
    """Fast mock translator that tracks memory consumption during processing."""

    def __init__(self) -> None:
        self.call_count = 0
        self.peak_rss_gb = 0.0

    def translate(
        self,
        chunk: Chunk,
        previous_context: str | tuple[str, str] | None = None,
    ) -> str:
        self.call_count += 1
        current_rss = get_current_rss_gb()
        self.peak_rss_gb = max(self.peak_rss_gb, current_rss)

        trans = f"[Traduzido]: {chunk.original_text[:100]}"
        chunk.translated_text = trans
        chunk.status = "translated"
        return trans


def test_streaming_memory_bounded(tmp_path: Path):
    """Fast test verifying that streaming window extraction stays well under 8 GB RAM."""
    pdf_path = tmp_path / "stream_25p.pdf"
    generate_synthetic_pdf(pdf_path, total_pages=25)

    extractor = DoclingExtractor(do_ocr=False, default_window_size=5)

    rss_before = get_current_rss_gb()
    blocks = extractor.extract(pdf_path)
    gc.collect()
    rss_after = get_current_rss_gb()

    assert len(blocks) >= 25
    # RNF12: Process RAM must remain <= 8.0 GB
    assert rss_after <= 8.0, f"RSS exceeded 8 GB: {rss_after:.2f} GB"
    logger.info(
        "Fast memory check: before=%.2f GB, after=%.2f GB",
        rss_before,
        rss_after,
    )


@pytest.mark.slow
def test_memory_and_vram_1000_pages(tmp_path: Path):
    """Slow integration test verifying RNF12, RNF13, and CA10:

    During processing of a 1000-page document:
    - RAM (RSS) <= 8 GB
    - VRAM <= 7 GB
    """
    pdf_path = Path(".cache/synthetic_1000p.pdf")
    if not pdf_path.is_file():
        generate_synthetic_pdf(pdf_path, total_pages=1000)

    assert pdf_path.is_file()

    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)
    translator = MemoryTrackTranslator()
    out_file = tmp_path / "big_output.md"

    peak_rss_gb = get_current_rss_gb()
    peak_vram_gb = get_gpu_vram_gb()

    # Sample real LLM inference to measure active GPU VRAM
    try:
        from tradutor_pdf.translation.ollama_client import OllamaClient

        client = OllamaClient()
        if client.is_healthy():
            client.generate(
                prompt="Sample text for memory benchmark",
                model="qwen2.5:7b-instruct-q4_K_M",
            )
            sample_vram = get_gpu_vram_gb()
            peak_vram_gb = max(peak_vram_gb, sample_vram)
            logger.info("Real LLM loaded; active VRAM: %.2f GB", sample_vram)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Ollama real LLM sample not available: %s", exc)

    t0 = time.time()
    logger.info(
        "Starting 1000-page translation (Initial RSS: %.2f GB, Initial VRAM: %.2f GB)",
        peak_rss_gb,
        peak_vram_gb,
    )

    run_cli(
        pdf_path=pdf_path,
        output_path=out_file,
        translator=translator,
        checkpoint_store=store,
        on_conflict="restart",
    )

    elapsed = time.time() - t0
    final_rss_gb = get_current_rss_gb()
    final_vram_gb = get_gpu_vram_gb()

    max_rss = max(peak_rss_gb, translator.peak_rss_gb, final_rss_gb)
    max_vram = max(peak_vram_gb, final_vram_gb)

    print(
        f"\n[BENCHMARK 1000P] Completed in {elapsed:.1f}s | "
        f"Peak RSS: {max_rss:.2f} GB (limit <= 8.0 GB) | "
        f"Peak VRAM: {max_vram:.2f} GB (limit <= 7.0 GB)"
    )

    # Validate CA10 and RNF12 criteria
    assert max_rss <= 8.0, (
        f"CA10 violated: Peak RSS {max_rss:.2f} GB exceeds 8.0 GB limit"
    )
    assert max_vram <= 7.0, (
        f"CA10 violated: Peak VRAM {max_vram:.2f} GB exceeds 7.0 GB limit"
    )
    assert out_file.is_file()
    assert out_file.stat().st_size > 0
