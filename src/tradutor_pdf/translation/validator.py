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
HEADING_LINE_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
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
        extra_structure_ratio: float = 0.1,
    ) -> None:
        self.min_length_ratio = min_length_ratio
        self.max_length_ratio = max_length_ratio
        self.extra_structure_ratio = extra_structure_ratio

    def max_extra_items(self, original_count: int) -> int:
        """Number of extra headings/list items tolerated over the original count.

        LLMs often repair malformed source structure (e.g. an orphan list item whose
        bullet was lost during extraction, or a standalone title line promoted to a
        heading). Such additions are harmless in small numbers; losing items is not.
        """
        return max(1, int(original_count * self.extra_structure_ratio))

    def _check_count(self, label: str, orig_count: int, resp_count: int) -> str | None:
        if resp_count < orig_count or resp_count - orig_count > self.max_extra_items(
            orig_count
        ):
            return (
                f"Quantidade de {label} diverge: original tem {orig_count}, "
                f"tradução tem {resp_count}"
            )
        return None

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

        # 4. Validate heading count (losing headings is an error; a few extras are tolerated)
        heading_error = self._check_count(
            "títulos",
            len(HEADING_PATTERN.findall(original_text)),
            len(HEADING_PATTERN.findall(cleaned)),
        )
        if heading_error:
            reasons.append(heading_error)

        # 5. Validate list item count (same tolerance as headings)
        list_error = self._check_count(
            "itens de lista",
            len(LIST_ITEM_PATTERN.findall(original_text)),
            len(LIST_ITEM_PATTERN.findall(cleaned)),
        )
        if list_error:
            reasons.append(list_error)

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


def demote_extra_headings(translation: str, original_text: str) -> str:
    """Turn headings the model invented back into plain paragraphs.

    Original headings are aligned in order to the translated ones, minimising the
    difference in heading level and relative position in the text. Translated headings
    left unmatched are extra and have their '#' markers removed.
    """
    orig = [
        (len(m.group(1)), m.start() / max(len(original_text), 1))
        for m in HEADING_LINE_PATTERN.finditer(original_text)
    ]
    resp_matches = list(HEADING_LINE_PATTERN.finditer(translation))
    n, m = len(resp_matches), len(orig)
    if n <= m:
        return translation

    resp = [
        (len(match.group(1)), match.start() / max(len(translation), 1))
        for match in resp_matches
    ]

    def cost(i: int, j: int) -> float:
        level_penalty = 0.0 if resp[i][0] == orig[j][0] else 1.0
        return level_penalty + abs(resp[i][1] - orig[j][1])

    # best[i][j]: minimal cost of matching the first j original headings
    # within the first i translated headings.
    inf = float("inf")
    best = [[inf] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        best[i][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, min(i, m) + 1):
            best[i][j] = min(
                best[i - 1][j],
                best[i - 1][j - 1] + cost(i - 1, j - 1),
            )

    extra: set[int] = set()
    i, j = n, m
    while i > 0:
        if j > 0 and best[i][j] == best[i - 1][j - 1] + cost(i - 1, j - 1):
            j -= 1
        else:
            extra.add(i - 1)
        i -= 1

    parts: list[str] = []
    last = 0
    for idx, match in enumerate(resp_matches):
        if idx in extra:
            logger.info(
                "Demoting extra heading not present in original: %r", match.group(0)
            )
            parts.append(translation[last : match.start()])
            parts.append(match.group(2))
            last = match.end()
    parts.append(translation[last:])
    return "".join(parts)


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
