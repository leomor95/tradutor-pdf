from __future__ import annotations

from tradutor_pdf.translation.validator import (
    TranslationValidator,
    validate_translation,
)


def test_validator_accepts_valid_translation() -> None:
    orig = "# Introduction\n\nThis is a clear explanation of §§INLINE_CODE_0§§.\n\n- Point 1\n- Point 2"
    resp = "# Introdução\n\nEsta é uma explicação clara de §§INLINE_CODE_0§§.\n\n- Ponto 1\n- Ponto 2"

    result = validate_translation(resp, orig)
    assert result.is_valid
    assert len(result.reasons) == 0


def test_validator_rejects_empty_response() -> None:
    orig = "Some text that needs translation."
    result = validate_translation("   \n  ", orig)
    assert not result.is_valid
    assert any("vazia" in r for r in result.reasons)


def test_validator_rejects_chat_phrases() -> None:
    orig = "This is a paragraph about software architecture."

    cases = [
        "Aqui está a tradução:\nEste é um parágrafo sobre arquitetura de software.",
        "Here is the translation:\nEste é um parágrafo sobre arquitetura.",
        "Tradução:\nEste é um parágrafo sobre arquitetura de software.",
        "Este é um parágrafo sobre software. Espero que ajude!",
        "Nota do tradutor: mantive os termos intactos.\nEste é um parágrafo.",
    ]

    for resp in cases:
        result = validate_translation(resp, orig)
        assert not result.is_valid, f"Expected reject for: {resp}"
        assert any("chat" in r.lower() for r in result.reasons)


def test_validator_rejects_heading_count_mismatch() -> None:
    orig = "# Title\n\n## Subtitle\n\nContent here."
    # Model dropped the subtitle
    resp = "# Título\n\nConteúdo aqui sem o subtítulo."

    result = validate_translation(resp, orig)
    assert not result.is_valid
    assert any("título" in r.lower() for r in result.reasons)


def test_validator_rejects_list_item_count_mismatch() -> None:
    orig = "Checklist:\n- Step 1\n- Step 2\n- Step 3"
    # Model only produced 2 list items
    resp = "Lista:\n- Passo 1\n- Passo 2"

    result = validate_translation(resp, orig)
    assert not result.is_valid
    assert any("lista" in r.lower() for r in result.reasons)


def test_validator_rejects_placeholder_mismatch() -> None:
    orig = "Use §§INLINE_CODE_0§§ and visit §§URL_0§§."
    # Model dropped the URL placeholder
    resp = "Use §§INLINE_CODE_0§§ e visite o site."

    result = validate_translation(resp, orig)
    assert not result.is_valid
    assert any("placeholder" in r.lower() for r in result.reasons)


def test_validator_rejects_length_too_short() -> None:
    orig = (
        "Distributed consensus algorithms like Raft and Paxos provide safety "
        "and liveness guarantees in asynchronous networks under crash-recovery models."
    )
    # Model only translated a tiny fragment
    resp = "Algoritmos seguros."

    result = validate_translation(resp, orig)
    assert not result.is_valid
    assert any("curto" in r.lower() for r in result.reasons)


def test_validator_rejects_length_too_long() -> None:
    orig = "Simple error code 404 means resource not found."
    # Model started hallucinating a lengthy guide
    resp = "O código de erro simples 404 significa recurso não encontrado. " * 5

    validator = TranslationValidator(max_length_ratio=2.0)
    result = validator.validate(resp, orig)
    assert not result.is_valid
    assert any("longo" in r.lower() for r in result.reasons)
