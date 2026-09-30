from __future__ import annotations

import logging

from tradutor_pdf.pipeline import Chunk, Translator
from tradutor_pdf.translation.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional technical translator specializing in translating technical documents from English to Brazilian Portuguese (pt-BR).

Instructions:
1. Translate the provided text accurately and naturally into Brazilian Portuguese (pt-BR).
2. Preserve all Markdown structure and formatting (headings, lists, bold, italics, links, inline code, code fences).
3. Do not alter code blocks, commands, or technical symbols.
4. Output ONLY the translated Markdown. Do not include introductory or concluding conversational remarks, notes, or explanations."""


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
    """Translates chunks using a local Ollama model with a basic en -> pt-BR prompt."""

    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
        target_language: str = "pt-BR",
        temperature: float = 0.2,
    ) -> None:
        self.client = client or OllamaClient()
        self.model = model or self.client.default_model
        self.target_language = target_language
        self.temperature = temperature

    def translate(
        self,
        chunk: Chunk,
        previous_context: str | None = None,
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

        prompt = f"Translate the following text to {self.target_language}:\n\n{chunk.original_text}"

        logger.info(
            "Translating chunk %s (%d tokens) with model %s",
            chunk.id,
            chunk.token_count,
            self.model,
        )

        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system=SYSTEM_PROMPT,
                temperature=self.temperature,
            )
            cleaned = strip_code_fence_wrapper(response)
            chunk.translated_text = cleaned
            chunk.status = "translated"
            return cleaned
        except Exception as exc:
            chunk.status = "error"
            chunk.error_message = str(exc)
            logger.error("Failed to translate chunk %s: %s", chunk.id, exc)
            raise
