from tradutor_pdf.pipeline import Chunk
from tradutor_pdf.translation.placeholders import (
    protect_placeholders,
    restore_placeholders,
)
from tradutor_pdf.translation.translator import OllamaTranslator


def test_protect_and_restore_inline_code():
    text = "Use `calculate_hash(data)` to verify the payload."
    protected, ph = protect_placeholders(text)
    assert "`calculate_hash(data)`" not in protected
    assert "__PH_0__" in protected
    assert ph["__PH_0__"] == "`calculate_hash(data)`"

    restored = restore_placeholders(protected, ph)
    assert restored == text


def test_protect_and_restore_urls():
    text = (
        "Documentation is at https://example.org/api/v1?ref=test and http://local.dev."
    )
    protected, ph = protect_placeholders(text)
    assert "https://example.org/api/v1?ref=test" not in protected
    assert "http://local.dev" not in protected
    assert len(ph) == 2

    restored = restore_placeholders(protected, ph)
    assert restored == text


def test_protect_and_restore_file_paths():
    text = (
        "Check /etc/tradutor/settings.toml, ./scripts/run.sh, ~/Documentos, "
        "and config/glossario.yaml."
    )
    protected, ph = protect_placeholders(text)
    assert "/etc/tradutor/settings.toml" not in protected
    assert "./scripts/run.sh" not in protected
    assert "~/Documentos" not in protected
    assert "config/glossario.yaml" not in protected
    assert len(ph) == 4

    restored = restore_placeholders(protected, ph)
    assert restored == text


def test_protect_and_restore_mixed():
    text = (
        "To test `make_request()`, browse https://docs.site.org/start "
        "and edit /var/log/app.log or `test_dir/file.py`."
    )
    protected, ph = protect_placeholders(text)
    restored = restore_placeholders(protected, ph)
    assert restored == text


def test_restore_tolerant_to_llm_variations():
    # LLM might lowercase or add slight spaces inside placeholder tokens
    ph = {
        "__PH_0__": "`inline_code()`",
        "__PH_1__": "https://example.org",
    }
    llm_output = "Consulte __ph_0__ ou visite __ PH_1 __ para ajuda."
    restored = restore_placeholders(llm_output, ph)
    assert (
        restored == "Consulte `inline_code()` ou visite https://example.org para ajuda."
    )


def test_translator_protects_and_restores_placeholders(fake_llm):
    # Mock LLM translating around placeholders
    def mock_gen(prompt: str) -> str:
        # Prompt should have __PH_0__ and __PH_1__, not the raw code or URL
        assert "`secret_fn()`" not in prompt
        assert "https://github.com/project" not in prompt
        assert "__PH_0__" in prompt
        assert "__PH_1__" in prompt
        return "Execute __PH_0__ e visite __PH_1__ para detalhes."

    fake_llm.custom_handler = mock_gen
    translator = OllamaTranslator(client=fake_llm)

    chunk = Chunk(
        id="c_ph",
        original_text="Run `secret_fn()` and visit https://github.com/project for details.",
        token_count=15,
    )

    result = translator.translate(chunk)
    assert (
        result
        == "Execute `secret_fn()` e visite https://github.com/project para detalhes."
    )
    assert chunk.translated_text == result
    assert chunk.status == "translated"
