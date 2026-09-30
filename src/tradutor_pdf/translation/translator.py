from __future__ import annotations

import logging
import re

from tradutor_pdf.config import GlossaryConfig, load_glossary
from tradutor_pdf.pipeline import Chunk, Translator
from tradutor_pdf.translation.glossary import (
    find_applicable_terms,
    verify_and_correct_translation,
)
from tradutor_pdf.translation.ollama_client import OllamaClient
from tradutor_pdf.translation.placeholders import (
    protect_placeholders,
    restore_placeholders,
)
from tradutor_pdf.translation.prompt import (
    build_translation_prompt,
    get_system_prompt,
)
from tradutor_pdf.translation.validator import (
    TranslationValidator,
)

logger = logging.getLogger(__name__)

_ECHOED_PREAMBLE_RE = re.compile(
    r"^(?:[#\s]*(?:Glossary|Glossário|Previous Context|Contexto Anterior)[^\n]*\n(?:.*?\n)*?)?"
    r"[#\s]*(?:Text to Translate|Texto a Traduzir|Texto para Traduzir)[^\n]*\n+",
    re.IGNORECASE,
)


def strip_echoed_preamble(text: str) -> str:
    """Remove any prompt section headers (e.g. ### Glossary Rules, ### Text to Translate) echoed by the LLM."""
    if not text:
        return text
    return _ECHOED_PREAMBLE_RE.sub("", text).strip()


def strip_code_fence_wrapper(text: str) -> str:
    """Strip outermost ```markdown ... ``` wrapper if the model enclosed its whole response in one."""
    stripped = text.strip()
    if stripped.startswith("```markdown\n") and stripped.endswith("\n```"):
        return stripped[len("```markdown\n") : -len("\n```")].strip()
    if stripped.startswith("```md\n") and stripped.endswith("\n```"):
        return stripped[len("```md\n") : -len("\n```")].strip()
    if (
        stripped.startswith("```\n")
        and stripped.endswith("\n```")
        and stripped.count("```") == 2
    ):
        return stripped[len("```\n") : -len("\n```")].strip()
    return stripped


class OllamaTranslator(Translator):
    """Translates chunks using a local Ollama model with glossary, context, validation, and retries."""

    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
        target_language: str = "pt-BR",
        temperature: float = 0.2,
        glossary: GlossaryConfig | None = None,
        max_retries: int = 3,
        validator: TranslationValidator | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or self.client.default_model
        self.target_language = target_language
        self.temperature = temperature
        self.glossary = glossary if glossary is not None else load_glossary()
        self.max_retries = max(1, max_retries)
        self.validator = validator or TranslationValidator()
        self._last_original: str | None = None
        self._last_translation: str | None = None

    def reset_context(self) -> None:
        """Reset accumulated previous context."""
        self._last_original = None
        self._last_translation = None

    def translate(
        self,
        chunk: Chunk,
        previous_context: str | tuple[str, str] | None = None,
    ) -> str:
        text = chunk.original_text.strip()
        if not text:
            chunk.translated_text = ""
            chunk.status = "translated"
            return ""

        # Check if all blocks are non-translatable
        if chunk.blocks and all(not b.translatable for b in chunk.blocks):
            chunk.translated_text = chunk.original_text
            chunk.status = "skipped"
            return chunk.original_text

        prev_orig: str | None = None
        prev_trans: str | None = None
        if isinstance(previous_context, tuple) and len(previous_context) == 2:
            prev_orig, prev_trans = previous_context
        elif isinstance(previous_context, str):
            prev_trans = previous_context
        elif previous_context is None and self._last_translation:
            prev_orig = self._last_original
            prev_trans = self._last_translation

        # Filter glossary terms that actually appear in this chunk
        app_preserve, app_trans = find_applicable_terms(
            chunk.original_text, self.glossary
        )

        protected_text, placeholders = protect_placeholders(chunk.original_text)

        prompt = build_translation_prompt(
            text=protected_text,
            target_language=self.target_language,
            glossary_preserve=app_preserve,
            glossary_translations=app_trans,
            previous_original=prev_orig,
            previous_translation=prev_trans,
        )

        system_prompt = get_system_prompt(self.target_language)

        last_error: str | None = None

        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "Translating chunk %s (attempt %d/%d, %d tokens) with model %s",
                chunk.id,
                attempt,
                self.max_retries,
                chunk.token_count,
                self.model,
            )

            try:
                response = self.client.generate(
                    prompt=prompt,
                    model=self.model,
                    system=system_prompt,
                    temperature=self.temperature,
                )
                cleaned = strip_echoed_preamble(strip_code_fence_wrapper(response))
                validation = self.validator.validate(
                    raw_response=cleaned,
                    original_text=protected_text,
                    placeholders=placeholders,
                )
                if not validation.is_valid:
                    reasons_str = "; ".join(validation.reasons)
                    logger.warning(
                        "Chunk %s attempt %d/%d failed validation: %s",
                        chunk.id,
                        attempt,
                        self.max_retries,
                        reasons_str,
                    )
                    last_error = f"Validation failed: {reasons_str}"
                    continue

                restored = restore_placeholders(cleaned, placeholders)
                corrected = verify_and_correct_translation(
                    restored, chunk.original_text, self.glossary
                )
                chunk.translated_text = corrected
                chunk.status = "translated"
                chunk.error_message = None
                self._last_original = chunk.original_text
                self._last_translation = corrected
                return corrected

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Chunk %s attempt %d/%d failed with exception: %s",
                    chunk.id,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = str(exc)

        # All attempts failed
        logger.error(
            "All %d attempts failed for chunk %s (%s). Falling back to original marked with <!-- NÃO TRADUZIDO -->.",
            self.max_retries,
            chunk.id,
            last_error,
        )
        fallback = f"<!-- NÃO TRADUZIDO -->\n\n{chunk.original_text}"
        chunk.translated_text = fallback
        chunk.status = "error"
        chunk.error_message = (
            last_error or f"Translation failed after {self.max_retries} attempts"
        )
        return fallback
