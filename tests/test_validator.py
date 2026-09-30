from __future__ import annotations

from tradutor_pdf.translation.validator import (
    TranslationValidator,
    demote_extra_headings,
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


def test_validator_tolerates_one_extra_heading_and_list_item() -> None:
    # Real case: the model promoted a title line to a heading and repaired a list
    # item whose bullet was lost during extraction.
    orig = (
        "LIMITED EDITION\n\n# THE BOOK\n\n# WARNING\n\n"
        "- . Trigger trauma\n\n- . Create harm\n\n. Result in injury"
    )
    resp = (
        "### Edição Limitada\n\n# O LIVRO\n\n# AVISO\n\n"
        "- Desencadear traumas\n\n- Criar danos\n\n- Resultar em lesões"
    )

    result = validate_translation(resp, orig)
    assert result.is_valid, result.reasons


def test_validator_rejects_too_many_extra_headings() -> None:
    orig = "# Title\n\nParagraph one.\n\nParagraph two.\n\nParagraph three."
    resp = "# Título\n\n## Parágrafo um.\n\n## Parágrafo dois.\n\n## Parágrafo três."

    result = validate_translation(resp, orig)
    assert not result.is_valid
    assert any("título" in r.lower() for r in result.reasons)


def test_validator_extra_tolerance_scales_with_original_count() -> None:
    validator = TranslationValidator()
    assert validator.max_extra_items(0) == 1
    assert validator.max_extra_items(8) == 1
    assert validator.max_extra_items(30) == 3


def test_demote_extra_headings_removes_invented_heading() -> None:
    orig = "LIMITED EDITION\n\n# THE BOOK\n\nText.\n\n# WARNING\n\nMore text."
    resp = "### Edição Limitada\n\n# O LIVRO\n\nTexto.\n\n# AVISO\n\nMais texto."

    result = demote_extra_headings(resp, orig)
    assert result == "Edição Limitada\n\n# O LIVRO\n\nTexto.\n\n# AVISO\n\nMais texto."


def test_demote_extra_headings_same_level_uses_position() -> None:
    orig = "# First\n\nBody one.\n\nMiddle line.\n\n# Last\n\nBody two."
    resp = "# Primeiro\n\nCorpo um.\n\n# Linha do meio.\n\n# Último\n\nCorpo dois."

    result = demote_extra_headings(resp, orig)
    assert (
        result == "# Primeiro\n\nCorpo um.\n\nLinha do meio.\n\n# Último\n\nCorpo dois."
    )


def test_demote_extra_headings_keeps_matching_structure() -> None:
    orig = "# A\n\n## B\n\nText."
    resp = "# A traduzido\n\n## B traduzido\n\nTexto."
    assert demote_extra_headings(resp, orig) == resp
