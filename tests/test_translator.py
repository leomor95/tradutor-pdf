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
    translator = OllamaTranslator(client=fake_llm, max_retries=3)
    chunk = Chunk(id="c4", original_text="Some text to translate")

    res = translator.translate(chunk)
    assert res.startswith("<!-- NÃO TRADUZIDO -->")
    assert "Some text to translate" in res
    assert chunk.status == "error"
    assert "Connection timed out" in chunk.error_message


def test_translate_retry_succeeds_after_validation_failure(fake_llm):
    # Attempt 1: chat preamble (fails validator)
    # Attempt 2: clean translation (succeeds)
    fake_llm.queue_responses(
        "Aqui está a tradução:\n# Introdução\n\nTexto traduzido.",
        "# Introdução\n\nTexto traduzido.",
    )
    translator = OllamaTranslator(client=fake_llm, max_retries=3)
    chunk = Chunk(id="c_retry", original_text="# Introduction\n\nTranslated text.")

    res = translator.translate(chunk)
    assert res == "# Introdução\n\nTexto traduzido."
    assert chunk.status == "translated"
    assert len(fake_llm.calls) == 2


def test_translate_all_retries_fail_validation_fallback(fake_llm):
    # All 3 attempts return chat preambles
    fake_llm.queue_responses(
        "Aqui está a tradução 1:\n# Introdução\n\nTexto.",
        "Aqui está a tradução 2:\n# Introdução\n\nTexto.",
        "Aqui está a tradução 3:\n# Introdução\n\nTexto.",
    )
    translator = OllamaTranslator(client=fake_llm, max_retries=3)
    chunk = Chunk(id="c_fail", original_text="# Introduction\n\nTranslated text.")

    res = translator.translate(chunk)
    assert res.startswith("<!-- NÃO TRADUZIDO -->")
    assert "# Introduction\n\nTranslated text." in res
    assert chunk.status == "error"
    assert "Validation failed" in chunk.error_message
    assert len(fake_llm.calls) == 3


def test_translate_with_glossary_filtering_and_correction(fake_llm):
    # LLM outputs "esteira" instead of "pipeline", and untranslated "machine learning"
    fake_llm.set_response("Nós construímos uma esteira usando machine learning.")
    translator = OllamaTranslator(client=fake_llm)

    chunk = Chunk(
        id="c5",
        original_text="We build a pipeline using machine learning.",
        token_count=10,
    )

    res = translator.translate(chunk)
    # The prompt should contain only the matching terms
    prompt = fake_llm.calls[0]["prompt"]
    assert "pipeline" in prompt
    assert "machine learning" in prompt
    assert "framework" not in prompt  # not in chunk, so not sent

    # The result should have corrected "esteira" -> "pipeline" and "machine learning" -> "aprendizado de máquina"
    assert "pipeline" in res
    assert "aprendizado de máquina" in res
    assert "esteira" not in res
    assert "machine learning" not in res


def test_translate_chains_context_automatically(fake_llm):
    fake_llm.set_response("Primeiro trecho traduzido.")
    translator = OllamaTranslator(client=fake_llm)

    chunk1 = Chunk(id="c1", original_text="First chunk original text.")
    translator.translate(chunk1)

    fake_llm.set_response("Segundo trecho traduzido.")
    chunk2 = Chunk(id="c2", original_text="Second chunk original text.")
    translator.translate(chunk2)

    assert len(fake_llm.calls) == 2
    second_prompt = fake_llm.calls[1]["prompt"]
    assert "### Previous Context" in second_prompt
    assert "First chunk original text." in second_prompt
    assert "Primeiro trecho traduzido." in second_prompt


def test_translate_explicit_context_overrides_stored(fake_llm):
    fake_llm.set_response("Resposta")
    translator = OllamaTranslator(client=fake_llm)

    chunk = Chunk(id="c1", original_text="Current text.")
    translator.translate(
        chunk,
        previous_context=("Explicit original text.", "Texto original explícito."),
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "### Previous Context" in prompt
    assert "Explicit original text." in prompt
    assert "Texto original explícito." in prompt


def test_translate_reset_context(fake_llm):
    fake_llm.set_response("Primeiro trecho.")
    translator = OllamaTranslator(client=fake_llm)

    chunk1 = Chunk(id="c1", original_text="First chunk.")
    translator.translate(chunk1)

    translator.reset_context()

    fake_llm.set_response("Segundo trecho.")
    chunk2 = Chunk(id="c2", original_text="Second chunk.")
    translator.translate(chunk2)

    second_prompt = fake_llm.calls[1]["prompt"]
    assert "### Previous Context" not in second_prompt
