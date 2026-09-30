from __future__ import annotations

PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT_TEMPLATE = """You are a professional technical translator specializing in translating technical documents into Brazilian Portuguese ({target_language}).

Strict rules:
1. Translate the provided text accurately and fluently into {target_language}.
2. Preserve all Markdown structure, syntax, and formatting exactly (headings #, bullet/numbered lists, emphasis, links, table structure).
3. Do NOT translate or modify placeholders (e.g. __PH_0__, __PH_1__, §§...§§). Keep all placeholder tokens exactly as they are in the translated text.
4. Adhere strictly to the provided glossary rules:
   - Terms under "Do not translate" MUST be kept verbatim in their original form.
   - Terms under "Translate as" MUST use the exact specified translation.
5. Do NOT add any comments, notes, conversational text, pleasantries, or markdown wrappers like ```markdown ... ``` around your entire answer.
6. Translate ONLY the document content under "### Text to Translate to {target_language}:". Never repeat, translate, or include prompt section headers such as "### Glossary Rules" or "### Text to Translate" in your output.
7. Output ONLY the translated Markdown text."""


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
    retry_feedback: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Build the structured user prompt with context and glossary instructions.

    ``retry_feedback`` lists why the previous attempt was rejected, so a retry does
    not resend an identical prompt and get an identical rejected answer.
    """
    sections: list[str] = []

    # 1. Previous context for terminology consistency
    if previous_original or previous_translation:
        context_lines = [
            "### Previous Context (for continuity and style only; do NOT re-translate):"
        ]
        if previous_original:
            orig = previous_original.strip()
            if len(orig) > 400:
                orig = "..." + orig[-400:]
            context_lines.append(f'Original:\n"""\n{orig}\n"""')
        if previous_translation:
            trans = previous_translation.strip()
            if len(trans) > 400:
                trans = "..." + trans[-400:]
            context_lines.append(f'Translated ({target_language}):\n"""\n{trans}\n"""')
        sections.append("\n\n".join(context_lines))

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

    # 3. Rejection reasons from the previous attempt
    if retry_feedback:
        feedback_lines = [
            "### Correction Required (your previous translation was rejected):",
            *(f"- {reason}" for reason in retry_feedback),
            (
                "Keep exactly the same Markdown structure as the source text: the same "
                "headings (lines starting with #) and the same list items. Do not turn "
                "plain lines into headings and do not add or remove list items."
            ),
        ]
        sections.append("\n".join(feedback_lines))

    # 4. Main content to translate
    sections.append(f"### Text to Translate to {target_language}:\n{text}")

    return "\n\n".join(sections)
