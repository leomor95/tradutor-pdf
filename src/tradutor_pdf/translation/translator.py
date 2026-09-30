from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)


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
    """Translates chunks using a local Ollama model with glossary, context, and validation."""

    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
        target_language: str = "pt-BR",
        temperature: float = 0.2,
        glossary: GlossaryConfig | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or self.client.default_model
        self.target_language = target_language
        self.temperature = temperature
        self.glossary = glossary if glossary is not None else load_glossary()

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

        logger.info(
            "Translating chunk %s (%d tokens) with model %s (glossary terms: %d preserve, %d translate)",
            chunk.id,
            chunk.token_count,
            self.model,
            len(app_preserve),
            len(app_trans),
        )

        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system=system_prompt,
                temperature=self.temperature,
            )
            cleaned = strip_code_fence_wrapper(response)
            restored = restore_placeholders(cleaned, placeholders)
            corrected = verify_and_correct_translation(
                restored, chunk.original_text, self.glossary
            )
            chunk.translated_text = corrected
            chunk.status = "translated"
            return corrected
        except Exception as exc:
            chunk.status = "error"
            chunk.error_message = str(exc)
            logger.error("Failed to translate chunk %s: %s", chunk.id, exc)
            raise
