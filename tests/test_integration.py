from pathlib import Path

from tradutor_pdf import run_cli
from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    get_default_output_path,
)
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.translator import OllamaTranslator
from tradutor_pdf.ui.worker import TranslationWorker


def test_full_pipeline_cli_integration(fake_llm, tmp_path: Path):
    fixture_pdf = (Path(__file__).parent / "fixtures" / "simple.pdf").resolve()
    assert fixture_pdf.is_file(), f"Fixture PDF not found at {fixture_pdf}"

    def mock_translation(prompt: str) -> str:
        if "Getting Started" in prompt:
            return "# Introdução à Computação Distribuída\n\nSistemas distribuídos permitem que múltiplos computadores coordenem e resolvam problemas computacionais de forma eficiente."
        if "Key Benefits" in prompt:
            return "## Principais Benefícios\n\n- Alta disponibilidade e tolerância a falhas.\n- Escalabilidade horizontal entre nós de trabalho."
        return "Texto traduzido em pt-BR."

    fake_llm.custom_handler = mock_translation
    translator = OllamaTranslator(client=fake_llm)
    output_md = tmp_path / "simple.pt-BR.md"

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=output_md,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == output_md
    assert output_md.is_file()
    content = output_md.read_text(encoding="utf-8")

    assert len(fake_llm.calls) >= 1
    assert "Introdução" in content or "Computação" in content or "pt-BR" in content


def test_full_pipeline_worker_integration(fake_llm, qtbot, tmp_path: Path):
    fixture_pdf = (Path(__file__).parent / "fixtures" / "simple.pdf").resolve()
    assert fixture_pdf.is_file()

    fake_llm.default_response = (
        "# Documento Traduzido\n\nConteúdo traduzido com sucesso."
    )
    translator = OllamaTranslator(client=fake_llm)
    expected_output = get_default_output_path(fixture_pdf)

    worker = TranslationWorker(
        source_path=fixture_pdf,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    finished_records = []
    worker.finished.connect(finished_records.append)

    with qtbot.waitSignal(worker.finished, timeout=30000):
        worker.start()

    assert len(finished_records) == 1
    out_file = finished_records[0]
    assert out_file == expected_output
    assert out_file.is_file()
    assert "Documento Traduzido" in out_file.read_text(encoding="utf-8")
