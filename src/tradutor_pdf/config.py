from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when configuration file is invalid or cannot be parsed."""


@dataclass(frozen=True)
class TranslationConfig:
    model: str = "qwen2.5:7b-instruct-q4_K_M"
    target_language: str = "pt-BR"
    chunk_max_tokens: int = 800
    max_retries: int = 3
    temperature: float = 0.2

    def __post_init__(self) -> None:
        if not self.model or not isinstance(self.model, str):
            raise ConfigError("Translation 'model' must be a non-empty string.")
        if not self.target_language or not isinstance(self.target_language, str):
            raise ConfigError(
                "Translation 'target_language' must be a non-empty string."
            )
        if not isinstance(self.chunk_max_tokens, int) or self.chunk_max_tokens <= 0:
            raise ConfigError(
                f"Translation 'chunk_max_tokens' must be a positive integer, got: {self.chunk_max_tokens}"
            )
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ConfigError(
                f"Translation 'max_retries' must be a non-negative integer, got: {self.max_retries}"
            )
        if not isinstance(self.temperature, (int, float)) or not (
            0.0 <= self.temperature <= 2.0
        ):
            raise ConfigError(
                f"Translation 'temperature' must be a float between 0.0 and 2.0, got: {self.temperature}"
            )


@dataclass(frozen=True)
class OCRConfig:
    engine: str = "tesseract"
    languages: tuple[str, ...] = ("eng",)

    def __post_init__(self) -> None:
        if not self.engine or not isinstance(self.engine, str):
            raise ConfigError("OCR 'engine' must be a non-empty string.")
        if not isinstance(self.languages, tuple) or not self.languages:
            raise ConfigError(
                "OCR 'languages' must be a non-empty list of language codes."
            )
        for lang in self.languages:
            if not isinstance(lang, str) or not lang.strip():
                raise ConfigError(
                    f"OCR language code must be a non-empty string, got: {lang!r}"
                )


@dataclass(frozen=True)
class OutputConfig:
    default_dir: str = "~/Documentos"

    def __post_init__(self) -> None:
        if not self.default_dir or not isinstance(self.default_dir, str):
            raise ConfigError("Output 'default_dir' must be a non-empty path string.")

    @property
    def resolved_dir(self) -> Path:
        return Path(self.default_dir).expanduser()


@dataclass(frozen=True)
class Settings:
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    ollama_host: str = "127.0.0.1:11434"

    def __post_init__(self) -> None:
        if not self.ollama_host or not isinstance(self.ollama_host, str):
            raise ConfigError("Settings 'ollama_host' must be a non-empty string.")


@dataclass(frozen=True)
class GlossaryConfig:
    preservar: tuple[str, ...] = ()
    traduzir_como: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.preservar, tuple):
            raise ConfigError("Glossary 'preservar' must be a list/tuple of strings.")
        for term in self.preservar:
            if not isinstance(term, str):
                raise ConfigError(
                    f"Glossary preserve term must be a string, got: {term!r}"
                )

        if not isinstance(self.traduzir_como, dict):
            raise ConfigError(
                "Glossary 'traduzir_como' must be a dictionary mapping string to string."
            )
        for src, dst in self.traduzir_como.items():
            if not isinstance(src, str) or not isinstance(dst, str):
                raise ConfigError(
                    f"Glossary translation pair must be strings, got: {src!r} -> {dst!r}"
                )


def find_project_root() -> Path:
    """Find project root directory by searching upward for pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def load_settings(path: Path | str | None = None) -> Settings:
    """Load settings from TOML file, falling back to defaults if not found."""
    if path is None:
        file_path = find_project_root() / "config" / "settings.toml"
    else:
        file_path = Path(path)

    ollama_host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")

    if not file_path.is_file():
        return Settings(ollama_host=ollama_host)

    try:
        with open(file_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Error parsing TOML file {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Invalid format in {file_path}: root must be a table")

    translation_data = data.get("translation", {})
    if not isinstance(translation_data, dict):
        raise ConfigError("Section [translation] must be a table")

    ocr_data = data.get("ocr", {})
    if not isinstance(ocr_data, dict):
        raise ConfigError("Section [ocr] must be a table")

    output_data = data.get("output", {})
    if not isinstance(output_data, dict):
        raise ConfigError("Section [output] must be a table")

    languages_raw = ocr_data.get("languages", ["eng"])
    if not isinstance(languages_raw, list):
        raise ConfigError("Field 'languages' in [ocr] must be a list of strings")

    translation_config = TranslationConfig(
        model=translation_data.get("model", "qwen2.5:7b-instruct-q4_K_M"),
        target_language=translation_data.get("target_language", "pt-BR"),
        chunk_max_tokens=translation_data.get("chunk_max_tokens", 800),
        max_retries=translation_data.get("max_retries", 3),
        temperature=float(translation_data.get("temperature", 0.2)),
    )

    ocr_config = OCRConfig(
        engine=ocr_data.get("engine", "tesseract"),
        languages=tuple(languages_raw),
    )

    output_config = OutputConfig(
        default_dir=output_data.get("default_dir", "~/Documentos"),
    )

    return Settings(
        translation=translation_config,
        ocr=ocr_config,
        output=output_config,
        ollama_host=ollama_host,
    )


def load_glossary(path: Path | str | None = None) -> GlossaryConfig:
    """Load glossary from YAML file, falling back to defaults if not found."""
    if path is None:
        file_path = find_project_root() / "config" / "glossario.yaml"
    else:
        file_path = Path(path)

    if not file_path.is_file():
        return GlossaryConfig()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise ConfigError(f"Error parsing YAML file {file_path}: {exc}") from exc

    if data is None:
        return GlossaryConfig()

    if not isinstance(data, dict):
        raise ConfigError(f"Invalid format in {file_path}: root must be a mapping")

    preservar_raw = data.get("preservar", [])
    if not isinstance(preservar_raw, list):
        raise ConfigError("Field 'preservar' in glossary must be a list of strings")

    traduzir_como_raw = data.get("traduzir_como", {})
    if not isinstance(traduzir_como_raw, dict):
        raise ConfigError("Field 'traduzir_como' in glossary must be a dictionary")

    return GlossaryConfig(
        preservar=tuple(preservar_raw),
        traduzir_como=dict(traduzir_como_raw),
    )
