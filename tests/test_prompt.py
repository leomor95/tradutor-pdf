from __future__ import annotations

from tradutor_pdf.translation.prompt import (
    PROMPT_VERSION,
    build_translation_prompt,
    get_system_prompt,
)


def test_prompt_version() -> None:
    assert PROMPT_VERSION == "1.0.0"


def test_system_prompt_rules() -> None:
    sys_prompt = get_system_prompt("pt-BR")
    assert "pt-BR" in sys_prompt
    assert "Preserve all Markdown structure" in sys_prompt
    assert "Do NOT translate or modify placeholders" in sys_prompt
    assert "glossary rules" in sys_prompt
    assert "Do NOT add any comments" in sys_prompt
    assert "Output ONLY the translated Markdown text" in sys_prompt


def test_build_translation_prompt_basic() -> None:
    prompt = build_translation_prompt("Hello world # Header")
    assert "### Text to Translate to pt-BR:\nHello world # Header" in prompt
    assert "Glossary Rules" not in prompt
    assert "Previous Context" not in prompt


def test_build_translation_prompt_with_glossary() -> None:
    prompt = build_translation_prompt(
        "There is a bug in the pipeline.",
        target_language="pt-BR",
        glossary_preserve=["bug", "pipeline"],
        glossary_translations={"machine learning": "aprendizado de máquina"},
    )
    assert "### Glossary Rules:" in prompt
    assert "Do not translate (preserve verbatim):" in prompt
    assert "- bug" in prompt
    assert "- pipeline" in prompt
    assert "Translate as specified:" in prompt
    assert '- "machine learning" -> "aprendizado de máquina"' in prompt
    assert "### Text to Translate to pt-BR:\nThere is a bug in the pipeline." in prompt


def test_build_translation_prompt_with_context() -> None:
    prompt = build_translation_prompt(
        "Next paragraph text.",
        target_language="pt-BR",
        previous_original="Previous paragraph original.",
        previous_translation="Parágrafo anterior traduzido.",
    )
    assert "### Previous Context" in prompt
    assert "Previous paragraph original." in prompt
    assert "Parágrafo anterior traduzido." in prompt
    assert "### Text to Translate to pt-BR:\nNext paragraph text." in prompt


def test_build_translation_prompt_truncates_long_context() -> None:
    long_prev_orig = "A" * 600
    long_prev_trans = "B" * 600
    prompt = build_translation_prompt(
        "Current text.",
        previous_original=long_prev_orig,
        previous_translation=long_prev_trans,
    )
    assert "...AAAA" in prompt
    assert "...BBBB" in prompt
