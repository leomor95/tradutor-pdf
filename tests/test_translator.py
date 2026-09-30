import pytest

from tradutor_pdf.pipeline import Block, BlockType, Chunk, Translator
from tradutor_pdf.translation.ollama_client import OllamaError
from tradutor_pdf.translation.translator import (
    OllamaTranslator,
    strip_code_fence_wrapper,
)


def test_translator_protocol(fake_llm):
    translator = OllamaTranslator(client=fake_llm)
    assert isinstance(translator, Translator)


def test_strip_code_fence_wrapper():
    wrapped = "```markdown\n# Título Traduzido\n\nTexto aqui.\n```"
    assert strip_code_fence_wrapper(wrapped) == "# Título Traduzido\n\nTexto aqui."

    wrapped_md = "```md\nParágrafo\n```"
    assert strip_code_fence_wrapper(wrapped_md) == "Parágrafo"

    unwrapped = "# Título Normal"
    assert strip_code_fence_wrapper(unwrapped) == "# Título Normal"


def test_translate_chunk_success(fake_llm):
    fake_llm.set_response("# Introdução ao Python\n\nPython é ótimo.")
    translator = OllamaTranslator(client=fake_llm)

    chunk = Chunk(
        id="c1",
        original_text="# Introduction to Python\n\nPython is great.",
        token_count=10,
    )

    res = translator.translate(chunk)
    assert res == "# Introdução ao Python\n\nPython é ótimo."
    assert chunk.translated_text == res
    assert chunk.status == "translated"
    assert len(fake_llm.calls) == 1
    assert "Introduction to Python" in fake_llm.calls[0]["prompt"]


def test_translate_empty_chunk(fake_llm):
    translator = OllamaTranslator(client=fake_llm)
    chunk = Chunk(id="c2", original_text="   ")

    res = translator.translate(chunk)
    assert res == ""
    assert chunk.status == "translated"
    assert len(fake_llm.calls) == 0


def test_translate_non_translatable_chunk(fake_llm):
    translator = OllamaTranslator(client=fake_llm)
    block = Block(
        id="b1",
        type=BlockType.CODE,
        content="x = 10",
        page=1,
        translatable=False,
    )
    chunk = Chunk(
        id="c3",
        blocks=[block],
        original_text="```python\nx = 10\n```",
    )

    res = translator.translate(chunk)
    assert res == "```python\nx = 10\n```"
    assert chunk.status == "skipped"
    assert len(fake_llm.calls) == 0


def test_translate_error_handling(fake_llm):
    fake_llm.should_fail = OllamaError("Connection timed out")
    translator = OllamaTranslator(client=fake_llm)
    chunk = Chunk(id="c4", original_text="Some text to translate")

    with pytest.raises(OllamaError):
        translator.translate(chunk)

    assert chunk.status == "error"
    assert "Connection timed out" in chunk.error_message
