from __future__ import annotations

import re

# Match HTTP/HTTPS URLs
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"'`]+")

# Match inline code snippets enclosed in backticks
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]+`")

# Match Unix absolute, relative, home paths and relative paths with file extensions
FILE_PATH_PATTERN = re.compile(
    r"(?:"
    r"(?:~|\.{1,2})/(?:[a-zA-Z0-9_.\-]+/?)+"  # ~/foo, ./bar, ../baz
    r"|/(?:[a-zA-Z0-9_.\-]+/)+[a-zA-Z0-9_.\-]+"  # /etc/foo.conf, /var/log/app.log
    r"|[a-zA-Z0-9_.\-]+/(?:[a-zA-Z0-9_.\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,6}"  # config/settings.toml
    r")"
)


def protect_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """Protect inline code, URLs, and file paths with placeholders before translation.

    Returns the transformed text containing placeholder tokens and a dictionary
    mapping each placeholder token to its original content.
    """
    if not text:
        return text, {}

    placeholders: dict[str, str] = {}
    counter = 0

    def get_ph(matched: str) -> str:
        nonlocal counter
        ph = f"__PH_{counter}__"
        counter += 1
        placeholders[ph] = matched
        return ph

    # 1. Protect inline code first (prevents interior URLs or paths from double matching)
    protected = INLINE_CODE_PATTERN.sub(lambda m: get_ph(m.group(0)), text)

    # 2. Protect URLs
    protected = URL_PATTERN.sub(lambda m: get_ph(m.group(0)), protected)

    # 3. Protect file paths
    protected = FILE_PATH_PATTERN.sub(lambda m: get_ph(m.group(0)), protected)

    return protected, placeholders


def restore_placeholders(text: str, placeholders: dict[str, str]) -> str:
    """Restore placeholders to their original strings after translation.

    Matches placeholders flexibly (case-insensitively and tolerating minor whitespace
    injections by LLM generation).
    """
    if not text or not placeholders:
        return text

    pattern = re.compile(r"__\s*PH_(\d+)\s*__", re.IGNORECASE)

    def repl_back(m: re.Match) -> str:
        idx = m.group(1)
        key = f"__PH_{idx}__"
        return placeholders.get(key, m.group(0))

    return pattern.sub(repl_back, text)
