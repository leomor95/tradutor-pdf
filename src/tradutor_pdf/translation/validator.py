from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Patterns that indicate unwanted conversational preamble or postscript from LLM
CHAT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:aqui está|segue|abaixo está|esta é)\s+(?:a\s+)?tradução",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*tradução:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*(?:here is|here's|below is|sure, here is|certainly, here is)\s+(?:the\s+)?translation",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*translation:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"\b(?:espero que (?:isso\s+)?ajude|se precisar de mais|qualquer dúvida|à disposição)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:hope this helps|let me know if you need|feel free to ask|as an ai language model)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*nota(?: do tradutor)?:\s*",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*translator's note:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*com certeza,\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*sure,\s*i\s+(?:have\s+)?translated",
        re.IGNORECASE | re.MULTILINE,
    ),
)

HEADING_PATTERN = re.compile(r"^#{1,6}\s+", re.MULTILINE)
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
PLACEHOLDER_PATTERN = re.compile(r"(?:__\s*PH_\d+\s*__|§§[A-Z0-9_]+§§)", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating an LLM translation response."""

    is_valid: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(is_valid=True, reasons=())

    @classmethod
    def reject(cls, *reasons: str) -> ValidationResult:
        return cls(is_valid=False, reasons=reasons)


class TranslationValidator:
    """Validates LLM translation output for structure fidelity, length ratio, and absence of chat remarks."""

    def __init__(
        self,
        min_length_ratio: float = 0.4,
        max_length_ratio: float = 2.5,
    ) -> None:
        self.min_length_ratio = min_length_ratio
        self.max_length_ratio = max_length_ratio

    def validate(
        self,
        raw_response: str,
        original_text: str,
        placeholders: dict[str, str] | None = None,
    ) -> ValidationResult:
        reasons: list[str] = []

        # 1. Reject if empty or only whitespace
        cleaned = raw_response.strip()
        if not cleaned:
            return ValidationResult.reject("A resposta do modelo veio vazia.")

        # 2. Reject conversational chat phrases
        for pat in CHAT_PATTERNS:
            match = pat.search(cleaned)
            if match:
                reasons.append(f"Frase de chat detectada: '{match.group(0).strip()}'")
                break

        # 3. Validate placeholder preservation
        if placeholders is not None:
            missing_placeholders: list[str] = []
            for ph_key in placeholders:
                m = re.match(r"^__PH_(\d+)__$", ph_key)
                if m:
                    ph_pat = re.compile(rf"__\s*PH_{m.group(1)}\s*__", re.IGNORECASE)
                else:
                    ph_pat = re.compile(re.escape(ph_key), re.IGNORECASE)

                if not ph_pat.search(cleaned):
                    missing_placeholders.append(ph_key)

            if missing_placeholders:
                reasons.append(
                    f"Divergência de placeholders: esperado {sorted(placeholders.keys())}, "
                    f"ausente(s): {missing_placeholders}"
                )
        else:
            orig_phs = sorted(PLACEHOLDER_PATTERN.findall(original_text))
            resp_phs = sorted(PLACEHOLDER_PATTERN.findall(cleaned))
            if len(orig_phs) != len(resp_phs):
                reasons.append(
                    f"Divergência de placeholders: esperado {orig_phs}, "
                    f"encontrado {resp_phs}"
                )

        # 4. Validate heading count
        orig_headings = HEADING_PATTERN.findall(original_text)
        resp_headings = HEADING_PATTERN.findall(cleaned)
        if len(orig_headings) != len(resp_headings):
            reasons.append(
                f"Quantidade de títulos diverge: original tem {len(orig_headings)}, "
                f"tradução tem {len(resp_headings)}"
            )

        # 5. Validate list item count
        orig_lists = LIST_ITEM_PATTERN.findall(original_text)
        resp_lists = LIST_ITEM_PATTERN.findall(cleaned)
        if len(orig_lists) != len(resp_lists):
            reasons.append(
                f"Quantidade de itens de lista diverge: original tem {len(orig_lists)}, "
                f"tradução tem {len(resp_lists)}"
            )

        # 6. Validate length within expected range
        orig_len = len(original_text.strip())
        resp_len = len(cleaned)
        if orig_len >= 30:
            ratio = resp_len / orig_len
            if ratio < self.min_length_ratio:
                reasons.append(
                    f"Tamanho muito curto: razão {ratio:.2f} < mínimo {self.min_length_ratio}"
                )
            elif ratio > self.max_length_ratio:
                reasons.append(
                    f"Tamanho muito longo: razão {ratio:.2f} > máximo {self.max_length_ratio}"
                )
        else:
            # Short text: avoid extreme runaway hallucinations
            if resp_len > orig_len * 4 + 25:
                reasons.append(
                    f"Tamanho excedeu limite para texto curto: {resp_len} caracteres"
                )

        if reasons:
            return ValidationResult.reject(*reasons)
        return ValidationResult.ok()


def validate_translation(
    raw_response: str,
    original_text: str,
    placeholders: dict[str, str] | None = None,
) -> ValidationResult:
    """Convenience helper function to validate a translation response."""
    return TranslationValidator().validate(
        raw_response=raw_response,
        original_text=original_text,
        placeholders=placeholders,
    )
