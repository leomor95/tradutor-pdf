from __future__ import annotations

from pathlib import Path

import pytest

from tradutor_pdf import run_cli
from tradutor_pdf.config import load_glossary
from tradutor_pdf.pipeline import Chunk
from tradutor_pdf.translation.glossary import (
    check_glossary_violations,
    term_in_text,
)
from tradutor_pdf.translation.translator import OllamaTranslator

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
TECHNICAL_PDF = FIXTURES_DIR / "technical_en.pdf"


def test_quality_with_fake_llm(fake_llm) -> None:
    """Fast test: verify glossary preservation and code block protection with fake_llm."""
    fake_llm.set_response(
        "A esteira de integração executa testes automáticos e detecta qualquer bug antes do deploy."
    )
    translator = OllamaTranslator(client=fake_llm)

    chunk = Chunk(
        id="c1",
        original_text="The pipeline runs automated tests and detects any bug before deploy.",
    )

    res = translator.translate(chunk)
    # The term 'esteira' must have been corrected back to 'pipeline'
    assert "pipeline" in res
    assert "bug" in res
    assert "deploy" in res
    assert "esteira" not in res


def test_technical_fixture_end_to_end_fake_llm(tmp_path: Path, fake_llm) -> None:
    """Fast test: verify pipeline execution on technical_en.pdf with fake_llm."""
    fake_llm.set_response(
        "Modernos processos de engenharia com pipeline e deploy automatizado para evitar bug."
    )
    output_md = tmp_path / "technical_translated.md"

    translator = OllamaTranslator(client=fake_llm)
    result_path = run_cli(
        pdf_path=TECHNICAL_PDF,
        output_path=output_md,
        translator=translator,
    )

    assert result_path.is_file()
    content = result_path.read_text(encoding="utf-8")

    # Code blocks must be preserved intact from the original document
    assert "def verify_commit_pipeline" in content
    assert "git commit -m" in content
    assert "pipeline" in content
    assert "bug" in content
    assert "deploy" in content


@pytest.mark.slow
def test_quality_real_llm_technical_terms(tmp_path: Path) -> None:
    """Slow integration test (CA06): verify 100% preservation of technical glossary terms with real LLM."""
    output_md = tmp_path / "technical_en.pt-BR.md"

    result_path = run_cli(
        pdf_path=TECHNICAL_PDF,
        output_path=output_md,
    )

    assert result_path.is_file()
    content = result_path.read_text(encoding="utf-8")

    # Verify absence of fallback non-translated markers
    assert "<!-- NÃO TRADUZIDO -->" not in content

    # CA06: 'bug', 'pipeline', and code blocks appear unaltered in 100% of occurrences
    assert term_in_text("bug", content), (
        "Preserved term 'bug' must be present in output"
    )
    assert term_in_text("pipeline", content), (
        "Preserved term 'pipeline' must be present in output"
    )
    assert term_in_text("deploy", content), (
        "Preserved term 'deploy' must be present in output"
    )
    assert term_in_text("commit", content), (
        "Preserved term 'commit' must be present in output"
    )
    assert term_in_text("framework", content), (
        "Preserved term 'framework' must be present in output"
    )

    # Fixed translation for 'machine learning' -> 'aprendizado de máquina'
    assert term_in_text("aprendizado de máquina", content), (
        "Term 'machine learning' must be translated as 'aprendizado de máquina'"
    )

    # Code blocks preserved verbatim
    assert "def verify_commit_pipeline" in content, (
        "Python code block must be preserved"
    )
    assert "git commit -m" in content, "Bash command block must be preserved"

    # Glossary compliance check
    glossary = load_glossary()
    orig_text = (FIXTURES_DIR / "sources" / "technical_en.typ").read_text(
        encoding="utf-8"
    )
    violations = check_glossary_violations(content, orig_text, glossary)
    assert violations == [], f"Detected glossary violations: {violations}"
