from pathlib import Path

import pytest
from fpdf import FPDF

from tradutor_pdf import run_cli
from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.config import Settings, TranslationConfig
from tradutor_pdf.pipeline import Block, BlockType, Chunk, Translator
from tradutor_pdf.ui.worker import TranslationWorker


class CountingTranslator(Translator):
    """Translator spy that records every chunk passed to translate()."""

    def __init__(self, prefix: str = "Traduzido: ") -> None:
        self.prefix = prefix
        self.call_count = 0
        self.translated_chunk_ids: list[str] = []

    def translate(
        self,
        chunk: Chunk,
        previous_context: str | tuple[str, str] | None = None,
    ) -> str:
        self.call_count += 1
        self.translated_chunk_ids.append(chunk.id)
        result = f"{self.prefix}{chunk.original_text}"
        chunk.translated_text = result
        chunk.status = "translated"
        return result


def create_multipage_pdf(file_path: Path, pages: int = 3) -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=12)
    for p in range(1, pages + 1):
        pdf.add_page()
        pdf.cell(
            w=0,
            h=10,
            text=f"Section {p} Title",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        for i in range(4):
            pdf.multi_cell(
                w=0,
                h=8,
                text=f"Paragraph {i} on page {p} describing distributed consensus and state machines in great detail with many explanatory words for testing segmentation.",
                new_x="LMARGIN",
                new_y="NEXT",
            )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(file_path))
    return file_path


def test_resume_skips_already_translated_chunks(tmp_path: Path):
    pdf_path = create_multipage_pdf(tmp_path / "resume_test.pdf", pages=3)
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    # First run: translate only chunk-0 into checkpoint manually to simulate mid-process interruption
    store.init_manifest(
        source_path=pdf_path,
        total_pages=3,
        model="test-model",
    )
    b0 = Block(
        id="b0",
        type=BlockType.PARAGRAPH,
        content="Section 1 Title",
        page=1,
    )
    c0 = Chunk(
        id="chunk-0",
        blocks=[b0],
        original_text="Section 1 Title",
        translated_text="Traduzido: Section 1 Title",
        page_start=1,
        page_end=1,
        status="translated",
    )
    store.save_chunk(pdf_path, c0, index=0)

    # Now run CLI with CountingTranslator
    translator = CountingTranslator()
    out_file = tmp_path / "output.md"

    run_cli(
        pdf_path=pdf_path,
        output_path=out_file,
        settings=Settings(translation=TranslationConfig(chunk_max_tokens=60)),
        translator=translator,
        checkpoint_store=store,
        on_conflict="reuse",
    )

    # Crucial assertion: chunk-0 must NOT be in translated_chunk_ids (zero double-translation)
    assert "chunk-0" not in translator.translated_chunk_ids
    assert translator.call_count >= 1

    # Output file contains translations for both chunk-0 and the rest
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Traduzido: Section 1 Title" in content

    # Manifest is now completed
    manifest = store.load_manifest(pdf_path)
    assert manifest is not None
    assert manifest.status == "completed"


def test_resume_worker_mid_process(tmp_path: Path, qtbot):
    pdf_path = create_multipage_pdf(tmp_path / "worker_test.pdf", pages=3)
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    # Simulate chunk-0 and chunk-1 already translated
    store.init_manifest(source_path=pdf_path, total_pages=3, model="test-model")
    c0 = Chunk(
        id="chunk-0",
        original_text="T1",
        translated_text="Traduzido T1",
        status="translated",
        page_start=1,
        page_end=1,
    )
    store.save_chunk(pdf_path, c0, index=0)

    translator = CountingTranslator()
    worker = TranslationWorker(
        source_path=pdf_path,
        output_path=tmp_path / "worker_out.md",
        translator=translator,
        checkpoint_store=store,
    )

    with qtbot.waitSignal(worker.finished, timeout=10000):
        worker.start()

    assert "chunk-0" not in translator.translated_chunk_ids
    assert (tmp_path / "worker_out.md").is_file()
    text = (tmp_path / "worker_out.md").read_text(encoding="utf-8")
    assert "Traduzido T1" in text


def test_resume_conflict_restart_vs_reuse(tmp_path: Path):
    pdf_path = create_multipage_pdf(tmp_path / "conflict_test.pdf", pages=2)
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)

    # Store checkpoint with old model
    store.init_manifest(
        source_path=pdf_path,
        total_pages=2,
        model="old-model-7b",
        prompt_version="0.9.0",
    )
    c0 = Chunk(
        id="chunk-0",
        original_text="Old Text",
        translated_text="Old Translation",
        status="translated",
    )
    store.save_chunk(pdf_path, c0, index=0)

    # Test restart: on_conflict="restart" clears old checkpoint and translates all chunks
    t_restart = CountingTranslator(prefix="Restart: ")
    out_file = tmp_path / "restart_out.md"
    run_cli(
        pdf_path=pdf_path,
        output_path=out_file,
        translator=t_restart,
        checkpoint_store=store,
        on_conflict="restart",
    )

    # Under restart, chunk-0 must be translated afresh
    assert "chunk-0" in t_restart.translated_chunk_ids
    text = out_file.read_text(encoding="utf-8")
    assert "Old Translation" not in text
    assert "Restart: " in text


def test_resume_interrupted_run_and_continue(tmp_path: Path):
    pdf_path = create_multipage_pdf(tmp_path / "interrupt_test.pdf", pages=3)
    cache_dir = tmp_path / ".cache"
    store = CheckpointStore(base_cache_dir=cache_dir)
    out_file = tmp_path / "interrupted_out.md"

    # Translator that translates 1 chunk then raises exception to simulate kill/crash
    class InterruptingTranslator(Translator):
        def __init__(self) -> None:
            self.call_count = 0

        def translate(
            self,
            chunk: Chunk,
            previous_context: str | tuple[str, str] | None = None,
        ) -> str:
            self.call_count += 1
            if self.call_count > 1:
                raise KeyboardInterrupt("Simulated process kill")
            chunk.translated_text = f"Part 1: {chunk.original_text}"
            chunk.status = "translated"
            return chunk.translated_text

    # First run fails mid-way
    with pytest.raises(KeyboardInterrupt):
        run_cli(
            pdf_path=pdf_path,
            output_path=out_file,
            settings=Settings(translation=TranslationConfig(chunk_max_tokens=60)),
            translator=InterruptingTranslator(),
            checkpoint_store=store,
            on_conflict="reuse",
        )

    # First chunk is in checkpoint
    assert store.has_checkpoint(pdf_path)
    manifest = store.load_manifest(pdf_path)
    assert manifest is not None
    assert manifest.status == "in_progress"

    # Second run resumes cleanly
    resuming_translator = CountingTranslator(prefix="Resumed: ")
    run_cli(
        pdf_path=pdf_path,
        output_path=out_file,
        settings=Settings(translation=TranslationConfig(chunk_max_tokens=60)),
        translator=resuming_translator,
        checkpoint_store=store,
        on_conflict="reuse",
    )

    # Verify no chunk was translated twice
    assert "chunk-0" not in resuming_translator.translated_chunk_ids
    assert out_file.is_file()
    final_text = out_file.read_text(encoding="utf-8")
    assert "Part 1: " in final_text
    assert "Resumed: " in final_text
