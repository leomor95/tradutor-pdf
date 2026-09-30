from __future__ import annotations

PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT_TEMPLATE = """You are a professional technical translator specializing in translating technical documents into Brazilian Portuguese ({target_language}).

Strict rules:
1. Translate the provided text accurately and fluently into {target_language}.
2. Preserve all Markdown structure, syntax, and formatting exactly (headings #, bullet/numbered lists, emphasis, links, table structure).
3. Do NOT translate or modify placeholders (e.g. §§INLINE_CODE_...§§, §§URL_...§§, §§PATH_...§§). Keep them exactly as they are.
4. Adhere strictly to the provided glossary rules:
   - Terms under "Do not translate" MUST be kept verbatim in their original form.
   - Terms under "Translate as" MUST use the exact specified translation.
5. Do NOT add any comments, notes, conversational text, pleasantries, or markdown wrappers like ```markdown ... ``` around your entire answer.
6. Output ONLY the translated Markdown text."""


def get_system_prompt(target_language: str = "pt-BR") -> str:
    """Return the fixed versioned system prompt configured for target language."""
    return SYSTEM_PROMPT_TEMPLATE.format(target_language=target_language)


def build_translation_prompt(
    text: str,
    target_language: str = "pt-BR",
    glossary_preserve: list[str] | tuple[str, ...] | None = None,
    glossary_translations: dict[str, str] | None = None,
    previous_original: str | None = None,
    previous_translation: str | None = None,
) -> str:
    """Build the structured user prompt with context and glossary instructions."""
    sections: list[str] = []

    # 1. Previous context for terminology consistency
    if previous_original and previous_translation:
        prev_orig_snippet = previous_original.strip()
        prev_trans_snippet = previous_translation.strip()
        # Truncate if too long (e.g. last ~300 chars or lines)
        if len(prev_orig_snippet) > 400:
            prev_orig_snippet = "..." + prev_orig_snippet[-400:]
        if len(prev_trans_snippet) > 400:
            prev_trans_snippet = "..." + prev_trans_snippet[-400:]

        context_block = (
            "### Previous Context (for continuity and style only; do NOT re-translate):\n"
            f'Original:\n"""\n{prev_orig_snippet}\n"""\n\n'
            f'Translated ({target_language}):\n"""\n{prev_trans_snippet}\n"""'
        )
        sections.append(context_block)

    # 2. Glossary terms applicable to this chunk
    glossary_lines: list[str] = []
    if glossary_preserve:
        glossary_lines.append("Do not translate (preserve verbatim):")
        for term in glossary_preserve:
            glossary_lines.append(f"- {term}")
    if glossary_translations:
        glossary_lines.append("Translate as specified:")
        for src, dst in glossary_translations.items():
            glossary_lines.append(f'- "{src}" -> "{dst}"')

    if glossary_lines:
        sections.append("### Glossary Rules:\n" + "\n".join(glossary_lines))

    # 3. Main content to translate
    sections.append(f"### Text to Translate to {target_language}:\n{text}")

    return "\n\n".join(sections)
