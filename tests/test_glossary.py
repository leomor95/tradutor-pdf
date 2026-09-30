from __future__ import annotations

from tradutor_pdf.config import GlossaryConfig
from tradutor_pdf.translation.glossary import (
    check_glossary_violations,
    find_applicable_terms,
    verify_and_correct_translation,
)

SAMPLE_GLOSSARY = GlossaryConfig(
    preservar=("bug", "pipeline", "deploy", "commit", "framework"),
    traduzir_como={
        "machine learning": "aprendizado de máquina",
        "thread": "thread",
    },
)


def test_find_applicable_terms_selective() -> None:
    text = "Fixing a bug in the CI/CD pipeline before tomorrow."
    preserve, translations = find_applicable_terms(text, SAMPLE_GLOSSARY)

    assert "bug" in preserve
    assert "pipeline" in preserve
    assert "deploy" not in preserve
    assert "commit" not in preserve
    assert "framework" not in preserve
    assert "machine learning" not in translations


def test_find_applicable_terms_plurals_and_case() -> None:
    text = "We investigated several Bugs and deployed two Pipelines with Machine Learning models."
    preserve, translations = find_applicable_terms(text, SAMPLE_GLOSSARY)

    assert "bug" in preserve
    assert "pipeline" in preserve
    assert "machine learning" in translations


def test_find_applicable_terms_none_matching() -> None:
    text = "This is a simple text about general algorithms and data structures."
    preserve, translations = find_applicable_terms(text, SAMPLE_GLOSSARY)

    assert preserve == []
    assert translations == {}


def test_verify_and_correct_traduzir_como_untranslated() -> None:
    orig = "We use machine learning for ranking."
    trans = "Nós usamos machine learning para classificação."

    corrected = verify_and_correct_translation(trans, orig, SAMPLE_GLOSSARY)
    assert "aprendizado de máquina" in corrected
    assert "machine learning" not in corrected


def test_verify_and_correct_traduzir_como_variant() -> None:
    orig = "Advanced machine learning techniques."
    trans = "Técnicas avançadas de aprendizagem de máquina."

    corrected = verify_and_correct_translation(trans, orig, SAMPLE_GLOSSARY)
    assert "aprendizado de máquina" in corrected
    assert "aprendizagem de máquina" not in corrected


def test_verify_and_correct_preservar_mistranslation() -> None:
    orig = "The build pipeline failed because of a bug."
    trans = "A esteira de integração falhou por causa de um defeito."

    corrected = verify_and_correct_translation(trans, orig, SAMPLE_GLOSSARY)
    assert "pipeline" in corrected
    assert "bug" in corrected
    assert "esteira de integração" not in corrected
    assert "defeito" not in corrected


def test_verify_and_correct_already_preserved() -> None:
    orig = "Deploy the commit immediately."
    trans = "Faça o deploy do commit imediatamente."

    corrected = verify_and_correct_translation(trans, orig, SAMPLE_GLOSSARY)
    assert corrected == trans


def test_check_glossary_violations() -> None:
    orig = "The bug in the pipeline using machine learning."
    bad_trans = "O erro no encanamento usando IA."

    violations = check_glossary_violations(bad_trans, orig, SAMPLE_GLOSSARY)
    assert any("bug" in v for v in violations)
    assert any("pipeline" in v for v in violations)
    assert any("aprendizado de máquina" in v for v in violations)

    good_trans = "O bug no pipeline usando aprendizado de máquina."
    assert check_glossary_violations(good_trans, orig, SAMPLE_GLOSSARY) == []
