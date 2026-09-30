#!/usr/bin/env python3
"""Benchmark script for tradutor-pdf (S8 / CA09 / RNF10 / RNF12).

Measures:
- Total execution time and time per page (target: <= 30s/page, <= 50 min for 100 pages).
- Peak RSS memory consumption (target: <= 8.0 GB).
- Peak GPU VRAM usage via nvidia-smi (target: <= 7.0 GB).
- Individual duration and throughput of each pipeline stage:
  - Extraction / OCR
  - Semantic segmentation
  - Local LLM translation
  - Markdown assembly
- Generates structured console output and detailed report in logs/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Ensure isolated directories
ROOT_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT_DIR / ".cache"))
os.environ.setdefault("HF_HOME", str(ROOT_DIR / ".cache" / "hf"))
os.environ.setdefault("UV_CACHE_DIR", str(ROOT_DIR / ".cache" / "uv"))
os.environ.setdefault("OLLAMA_MODELS", str(ROOT_DIR / "models"))
os.environ.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

if (ROOT_DIR / "bin" / "tessdata").is_dir():
    os.environ.setdefault("TESSDATA_PREFIX", str(ROOT_DIR / "bin" / "tessdata"))

if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

import psutil

from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    get_default_output_path,
)
from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.config import load_settings
from tradutor_pdf.extraction.docling_extractor import (
    DoclingExtractor,
    get_pdf_page_count,
)
from tradutor_pdf.logging_setup import setup_logging
from tradutor_pdf.pipeline import Chunk
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.prompt import PROMPT_VERSION
from tradutor_pdf.translation.translator import OllamaTranslator


class ResourceSampler:
    """Samples RSS memory and GPU VRAM periodically in a background daemon thread."""

    def __init__(self, interval_sec: float = 0.25) -> None:
        self.interval = interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_rss_bytes: int = 0
        self.peak_vram_mib: float = 0.0
        self.peak_app_vram_mib: float = 0.0
        self.gpu_detected: bool = False

    def start(self) -> None:
        self._stop_event.clear()
        self.peak_rss_bytes = 0
        self.peak_vram_mib = 0.0
        self.peak_app_vram_mib = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _get_process_rss(self) -> int:
        try:
            proc = psutil.Process()
            rss = proc.memory_info().rss
            for child in proc.children(recursive=True):
                try:
                    rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return rss
        except Exception:  # noqa: BLE001
            return 0

    def _get_gpu_vram_info(self) -> tuple[float, float]:
        """Return (system_vram_mib, model_vram_mib)."""
        sys_vram = 0.0
        model_vram = 0.0
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            first_line = out.strip().splitlines()[0]
            sys_vram = float(first_line)
            self.gpu_detected = True
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            apps_out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-compute-apps=process_name,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            for line in apps_out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2 and any(
                    k in parts[0] for k in ("ollama", "llama", "python")
                ):
                    try:
                        model_vram += float(parts[1])
                    except ValueError:
                        pass
        except Exception:  # noqa: BLE001, S110
            pass

        return sys_vram, model_vram

    def _run(self) -> None:
        while not self._stop_event.is_set():
            rss = self._get_process_rss()
            sys_vram, model_vram = self._get_gpu_vram_info()

            self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
            self.peak_vram_mib = max(self.peak_vram_mib, sys_vram)
            self.peak_app_vram_mib = max(self.peak_app_vram_mib, model_vram)

            self._stop_event.wait(self.interval)


@dataclass
class StageMetric:
    name: str
    duration_sec: float
    percentage: float


@dataclass
class BenchmarkReport:
    pdf_path: str
    total_pages: int
    total_blocks: int
    total_chunks: int
    total_time_sec: float
    time_per_page_sec: float
    peak_rss_gb: float
    peak_vram_gb: float
    peak_model_vram_gb: float
    stages: list[StageMetric]
    criterias: dict[str, bool]


def ensure_pdf_exists(pdf_path: Path, pages: int = 100) -> Path:
    """Ensure benchmark PDF fixture exists, generating it if absent."""
    if pdf_path.is_file():
        return pdf_path

    print(
        f"[INFO] Fixture '{pdf_path}' não encontrada. Gerando synthetic PDF ({pages} páginas)..."
    )
    from scripts.gen_big_pdf import generate_synthetic_pdf

    generate_synthetic_pdf(output_path=pdf_path, total_pages=pages)
    return pdf_path


def run_benchmark(
    pdf_path: Path,
    output_path: Path | None = None,
    restart: bool = True,
    sample_pages: int | None = None,
) -> BenchmarkReport:
    """Execute complete benchmark measuring time, memory, VRAM and stage metrics."""
    setup_logging()
    settings = load_settings()

    source = ensure_pdf_exists(pdf_path, pages=100)
    total_pages = get_pdf_page_count(source)

    if sample_pages and sample_pages < total_pages:
        target_pages = (1, sample_pages)
        effective_pages = sample_pages
    else:
        target_pages = (1, total_pages)
        effective_pages = total_pages

    dest = output_path or get_default_output_path(source)
    store = CheckpointStore()

    if restart and store.has_checkpoint(source):
        print(
            f"[INFO] Limpando checkpoint existente para benchmark limpo ({source.name})..."
        )
        store.clear(source)

    sampler = ResourceSampler(interval_sec=0.25)
    sampler.start()

    print("=" * 70)
    print(f" INICIANDO BENCHMARK: {source.name} ({effective_pages} páginas)")
    print(f" Modelo: {settings.translation.model}")
    print(f" Destino MD: {dest}")
    print("=" * 70)

    t_start = time.perf_counter()

    # --- Stage 1: Extraction / OCR ---
    print(f"[1/4] Extração / OCR ({effective_pages} páginas)...")
    t0_extract = time.perf_counter()
    extractor = DoclingExtractor(
        do_ocr="auto",
        ocr_languages=settings.ocr.languages,
        min_text_chars=settings.ocr.min_chars,
    )
    blocks = extractor.extract(source, pages=target_pages)
    t_extract = time.perf_counter() - t0_extract
    print(
        f"      Extração concluída: {len(blocks)} blocos em {t_extract:.2f}s "
        f"({t_extract / effective_pages:.2f}s/pág)"
    )

    # --- Stage 2: Semantic Segmentation ---
    print("[2/4] Segmentação semântica...")
    t0_seg = time.perf_counter()
    segmenter = SemanticSegmenter()
    chunks = segmenter.segment(blocks, max_tokens=settings.translation.chunk_max_tokens)
    t_seg = time.perf_counter() - t0_seg
    print(f"      Segmentação concluída: {len(chunks)} trechos em {t_seg:.2f}s")

    # --- Stage 3: Translation ---
    print(f"[3/4] Tradução LLM ({len(chunks)} trechos)...")
    t0_trans = time.perf_counter()
    translator = OllamaTranslator(
        model=settings.translation.model,
        target_language=settings.translation.target_language,
        temperature=settings.translation.temperature,
    )

    store.init_manifest(
        source_path=source,
        total_pages=effective_pages,
        model=settings.translation.model,
        prompt_version=PROMPT_VERSION,
        target_language=settings.translation.target_language,
    )

    assembler = MarkdownAssembler()
    prev_chunk: Chunk | None = None

    for idx, chunk in enumerate(chunks):
        if store.is_chunk_completed(source, chunk.id):
            chunk.translated_text = store.load_chunk_translation(source, chunk.id)
            chunk.status = "translated"
            prev_chunk = chunk
            continue

        chunk_t0 = time.perf_counter()
        prev_context = (
            (prev_chunk.original_text, prev_chunk.translated_text)
            if prev_chunk and prev_chunk.translated_text
            else None
        )
        translator.translate(chunk, previous_context=prev_context)
        chunk_elapsed = time.perf_counter() - chunk_t0

        store.save_chunk(source, chunk, index=idx)
        assembler.append_chunk(chunk, dest)

        if chunk.status == "translated":
            prev_chunk = chunk

        if (idx + 1) % 10 == 0 or (idx + 1) == len(chunks):
            current_elapsed = time.perf_counter() - t0_trans
            avg_chunk = current_elapsed / (idx + 1)
            eta_sec = avg_chunk * (len(chunks) - (idx + 1))
            print(
                f"      Progresso: {idx + 1}/{len(chunks)} trechos "
                f"({(idx + 1) / len(chunks) * 100:.1f}%) | "
                f"último: {chunk_elapsed:.2f}s | "
                f"ETA: {eta_sec / 60:.1f} min"
            )

    t_trans = time.perf_counter() - t0_trans
    print(
        f"      Tradução concluída: {len(chunks)} trechos em {t_trans:.2f}s "
        f"({t_trans / effective_pages:.2f}s/pág)"
    )

    # --- Stage 4: Assembly ---
    print("[4/4] Montagem final do Markdown...")
    t0_assem = time.perf_counter()
    final_path = assembler.assemble(chunks, dest)
    store.mark_completed(source)
    t_assem = time.perf_counter() - t0_assem
    print(f"      Montagem concluída em {t_assem:.2f}s -> {final_path}")

    total_time = time.perf_counter() - t_start
    sampler.stop()

    peak_rss_gb = sampler.peak_rss_bytes / (1024**3)
    peak_vram_gb = sampler.peak_vram_mib / 1024.0
    peak_model_vram_gb = (
        sampler.peak_app_vram_mib / 1024.0
        if sampler.peak_app_vram_mib > 0
        else peak_vram_gb
    )
    sec_per_page = total_time / effective_pages

    stages = [
        StageMetric("Extração / OCR", t_extract, (t_extract / total_time) * 100),
        StageMetric("Segmentação", t_seg, (t_seg / total_time) * 100),
        StageMetric("Tradução LLM", t_trans, (t_trans / total_time) * 100),
        StageMetric("Montagem MD", t_assem, (t_assem / total_time) * 100),
    ]

    criterias = {
        "CA09 (Tempo 100p <= 50 min)": total_time <= 3000.0
        if effective_pages >= 100
        else True,
        "RNF10 (Tempo médio <= 30s/página)": sec_per_page <= 30.0,
        "RNF12 (RAM pico <= 8.0 GB)": peak_rss_gb <= 8.0,
        "RNF12 (VRAM modelo <= 7.0 GB)": peak_model_vram_gb <= 7.0
        if sampler.gpu_detected
        else True,
    }

    report = BenchmarkReport(
        pdf_path=str(source),
        total_pages=effective_pages,
        total_blocks=len(blocks),
        total_chunks=len(chunks),
        total_time_sec=total_time,
        time_per_page_sec=sec_per_page,
        peak_rss_gb=peak_rss_gb,
        peak_vram_gb=peak_vram_gb,
        peak_model_vram_gb=peak_model_vram_gb,
        stages=stages,
        criterias=criterias,
    )

    # Print summary
    print("\n" + "=" * 70)
    print(" RELATÓRIO DO BENCHMARK")
    print("=" * 70)
    print(f" Documento:           {source.name}")
    print(f" Páginas processadas: {effective_pages}")
    print(f" Blocos extraídos:    {len(blocks)}")
    print(f" Trechos semânticos:  {len(chunks)}")
    print("-" * 70)
    print(f" Tempo total:         {total_time:.2f}s ({total_time / 60:.2f} min)")
    print(f" Tempo por página:    {sec_per_page:.2f}s / página")
    print(f" Pico de RAM (RSS):   {peak_rss_gb:.2f} GB")
    print(f" Pico VRAM Modelo:    {peak_model_vram_gb:.2f} GB (RNF12 <= 7.0 GB)")
    print(f" Pico VRAM Sistema:   {peak_vram_gb:.2f} GB (GPU 8.0 GB)")
    print("-" * 70)
    print(" Duração por etapa:")
    for stg in stages:
        print(
            f"   - {stg.name:<18}: {stg.duration_sec:>8.2f}s ({stg.percentage:>5.1f}%)"
        )
    print("-" * 70)
    print(" Critérios de Aceite e Metas Não Funcionais:")
    for crit, passed in criterias.items():
        status_str = "[APROVADO]" if passed else "[FALHOU]"
        print(f"   {status_str} {crit}")
    print("=" * 70 + "\n")

    # Save reports to logs
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = log_dir / "benchmark_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    print(f"[OK] Relatório salvo em: {report_json_path}")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Executa o benchmark de desempenho e memória (S8 / CA09 / RNF10 / RNF12)",
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=ROOT_DIR / "tests" / "fixtures" / "book_100p.pdf",
        help="Caminho do PDF para teste (padrão: tests/fixtures/book_100p.pdf)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Caminho de saída para o Markdown traduzido",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Reaproveita checkpoint se já existir ao invés de reiniciar do zero",
    )
    parser.add_argument(
        "--sample-pages",
        type=int,
        help="Limita o benchmark a um número menor de páginas para teste rápido",
    )

    args = parser.parse_args(argv)
    report = run_benchmark(
        pdf_path=args.pdf,
        output_path=args.output,
        restart=not args.no_restart,
        sample_pages=args.sample_pages,
    )

    # Return 0 if all criteria passed, else 1
    if all(report.criterias.values()):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
