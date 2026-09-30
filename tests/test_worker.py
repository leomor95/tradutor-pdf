from pathlib import Path

from tradutor_pdf.pipeline import Block, BlockType, Extractor, Translator
from tradutor_pdf.ui.worker import TranslationWorker


class StubExtractor(Extractor):
    def __init__(self, blocks: list[Block]) -> None:
        self.blocks = blocks

    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
    ) -> list[Block]:
        return self.blocks


class StubTranslator(Translator):
    def translate(
        self,
        chunk,
        previous_context: str | None = None,
    ) -> str:
        res = f"TRADUZIDO: {chunk.original_text}"
        chunk.translated_text = res
        chunk.status = "translated"
        return res


def test_worker_success(qtbot, tmp_path: Path):
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4...")
    output_md = tmp_path / "out.md"

    blocks = [
        Block(
            id="b1",
            type=BlockType.HEADING,
            content="Hello",
            page=1,
            metadata={"heading_level": 1},
        ),
        Block(id="b2", type=BlockType.PARAGRAPH, content="World", page=1),
    ]

    worker = TranslationWorker(
        source_path=dummy_pdf,
        output_path=output_md,
        extractor=StubExtractor(blocks),
        translator=StubTranslator(),
    )

    progress_records = []
    finished_records = []

    worker.progress.connect(lambda d, t: progress_records.append((d, t)))
    worker.finished.connect(lambda p: finished_records.append(p))

    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()

    assert len(finished_records) == 1
    assert finished_records[0] == output_md
    assert output_md.exists()
    content = output_md.read_text(encoding="utf-8")
    assert "TRADUZIDO:" in content
    assert len(progress_records) >= 2


def test_worker_missing_file_fails(qtbot, tmp_path: Path):
    worker = TranslationWorker(
        source_path=tmp_path / "missing.pdf",
    )

    failed_records = []
    worker.failed.connect(lambda err: failed_records.append(err))

    with qtbot.waitSignal(worker.failed, timeout=5000):
        worker.start()

    assert len(failed_records) == 1
    assert "não encontrado" in failed_records[0]
