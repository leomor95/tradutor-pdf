from __future__ import annotations

import logging
import re

from tradutor_pdf.config import GlossaryConfig

logger = logging.getLogger(__name__)

# Known Portuguese translations/mistranslations that LLMs may produce for common tech terms
KNOWN_PRESERVE_MISTRANSLATIONS: dict[str, dict[str, str]] = {
    "bug": {
        "insetos": "bugs",
        "inseto": "bug",
        "defeitos": "bugs",
        "defeito": "bug",
    },
    "pipeline": {
        "esteiras de integração": "pipelines",
        "esteira de integração": "pipeline",
        "esteiras de entrega": "pipelines",
        "esteira de entrega": "pipeline",
        "esteiras": "pipelines",
        "esteira": "pipeline",
        "encanamentos": "pipelines",
        "encanamento": "pipeline",
        "dutos": "pipelines",
        "duto": "pipeline",
        "canalizações": "pipelines",
        "canalização": "pipeline",
    },
    "deploy": {
        "implantações": "deploys",
        "implantação": "deploy",
        "desdobramentos": "deploys",
        "desdobramento": "deploy",
    },
    "commit": {
        "confirmações": "commits",
        "confirmação": "commit",
        "submissões": "commits",
        "submissão": "commit",
    },
    "framework": {
        "arcabouços": "frameworks",
        "arcabouço": "framework",
        "quadros de trabalho": "frameworks",
        "quadro de trabalho": "framework",
        "estruturas de software": "frameworks",
        "estrutura de software": "framework",
    },
}

# Known Portuguese variants for translation targets in traduzir_como
KNOWN_TRANSLATION_VARIANTS: dict[str, list[str]] = {
    "aprendizado de máquina": [
        "aprendizagem de máquina",
        "aprendizado automático",
        "aprendizagem automática",
    ],
}


def _term_pattern(term: str, allow_plural: bool = True) -> re.Pattern[str]:
    """Build a regex pattern for matching a term with word boundary awareness and optional plural."""
    escaped = re.escape(term)
    plural_suffix = r"(?:s|es)?" if allow_plural and term.isalnum() else ""
    prefix = r"\b" if (term and (term[0].isalnum() or term[0] == "_")) else r"(?:\B|^)"
    suffix = (
        r"\b" if (term and (term[-1].isalnum() or term[-1] == "_")) else r"(?:\B|$)"
    )
    return re.compile(rf"{prefix}{escaped}{plural_suffix}{suffix}", re.IGNORECASE)


def term_in_text(term: str, text: str, allow_plural: bool = True) -> bool:
    """Check if a term (or its plural) appears in text with word boundary checking."""
    pattern = _term_pattern(term, allow_plural=allow_plural)
    return bool(pattern.search(text))


def find_applicable_terms(
    text: str,
    glossary: GlossaryConfig,
) -> tuple[list[str], dict[str, str]]:
    """Scan text and return only the glossary terms that actually appear in this chunk."""
    if not text:
        return [], {}

    applicable_preserve: list[str] = [
        term for term in glossary.preservar if term_in_text(term, text)
    ]

    applicable_translations: dict[str, str] = {
        src: dst
        for src, dst in glossary.traduzir_como.items()
        if term_in_text(src, text)
    }

    return applicable_preserve, applicable_translations


def verify_and_correct_translation(
    translated_text: str,
    original_text: str,
    glossary: GlossaryConfig,
) -> str:
    """Post-translation verification and correction for terms in 'preservar' and 'traduzir_como'."""
    result = translated_text

    # 1. Process traduzir_como: ensure specified translations are used
    for src, dst in glossary.traduzir_como.items():
        if not term_in_text(src, original_text):
            continue

        # If dst is already the exact same as src (e.g. thread -> thread), treat as preserve
        if src.strip().lower() == dst.strip().lower():
            if not term_in_text(src, result) and src.lower() == "thread":
                # Look for mistranslations if any
                result = re.sub(
                    r"\b(fios? de execução|linhas? de execução)\b",
                    "thread",
                    result,
                    flags=re.IGNORECASE,
                )
            continue

        # Check if known variants of dst were generated instead of dst
        variants = KNOWN_TRANSLATION_VARIANTS.get(dst.lower(), [])
        for var in variants:
            var_pat = re.compile(rf"\b{re.escape(var)}\b", re.IGNORECASE)
            if var_pat.search(result):
                logger.info("Correcting variant '%s' to '%s' in translation", var, dst)
                result = var_pat.sub(dst, result)

        # If the English source term was left untranslated in the output, replace it with dst
        src_pat = re.compile(rf"\b{re.escape(src)}\b", re.IGNORECASE)
        if src_pat.search(result) and not term_in_text(dst, result):
            logger.info("Replacing untranslated source term '%s' with '%s'", src, dst)
            result = src_pat.sub(dst, result)

    # 2. Process preservar: ensure preserved terms are kept verbatim
    for term in glossary.preservar:
        if not term_in_text(term, original_text):
            continue

        # If the term is already present in translated text, all is good
        if term_in_text(term, result):
            continue

        # If missing from translated text, check known mistranslations
        mistranslations = KNOWN_PRESERVE_MISTRANSLATIONS.get(term.lower(), {})
        corrected = False
        for wrong, right in mistranslations.items():
            wrong_pat = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
            if wrong_pat.search(result):
                logger.info(
                    "Correcting mistranslation '%s' back to preserved term '%s'",
                    wrong,
                    right,
                )
                result = wrong_pat.sub(right, result)
                corrected = True

        if not corrected and not term_in_text(term, result):
            logger.warning(
                "Preserved term '%s' from original text was not detected in translation.",
                term,
            )

    return result


def check_glossary_violations(
    translated_text: str,
    original_text: str,
    glossary: GlossaryConfig,
) -> list[str]:
    """Return a list of glossary violations detected in the translated text."""
    violations: list[str] = []

    for term in glossary.preservar:
        if term_in_text(term, original_text) and not term_in_text(
            term, translated_text
        ):
            violations.append(f"Preserved term '{term}' is missing from translation.")

    for src, dst in glossary.traduzir_como.items():
        if term_in_text(src, original_text) and not term_in_text(dst, translated_text):
            violations.append(
                f"Translation target '{dst}' for source '{src}' is missing from translation."
            )

    return violations
