from pathlib import Path

import pytest

from tradutor_pdf.config import (
    ConfigError,
    Settings,
    load_glossary,
    load_settings,
)


def test_load_default_settings(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "non_existent.toml")
    assert isinstance(settings, Settings)
    assert settings.translation.model == "qwen2.5:7b-instruct-q4_K_M"
    assert settings.translation.target_language == "pt-BR"
    assert settings.translation.chunk_max_tokens == 800
    assert settings.translation.max_retries == 3
    assert settings.translation.temperature == 0.2
    assert settings.ocr.engine == "tesseract"
    assert settings.ocr.languages == ("eng",)
    assert settings.output.default_dir == "~/Documentos"


def test_load_existing_config_settings() -> None:
    settings = load_settings()
    assert settings.translation.model == "qwen2.5:7b-instruct-q4_K_M"
    assert settings.ocr.languages == ("eng",)
    assert settings.output.default_dir == "~/Documentos"


def test_load_existing_glossary() -> None:
    glossary = load_glossary()
    assert "bug" in glossary.preservar
    assert "pipeline" in glossary.preservar
    assert glossary.traduzir_como.get("machine learning") == "aprendizado de máquina"
    assert glossary.traduzir_como.get("thread") == "thread"


def test_invalid_toml_syntax(tmp_path: Path) -> None:
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("translation: [invalid toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="Error parsing TOML"):
        load_settings(bad_toml)


def test_invalid_chunk_max_tokens(tmp_path: Path) -> None:
    toml_file = tmp_path / "settings.toml"
    toml_file.write_text("[translation]\nchunk_max_tokens = -5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="chunk_max_tokens"):
        load_settings(toml_file)


def test_invalid_temperature(tmp_path: Path) -> None:
    toml_file = tmp_path / "settings.toml"
    toml_file.write_text("[translation]\ntemperature = 3.5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="temperature"):
        load_settings(toml_file)


def test_invalid_yaml_syntax(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("preservar: [unclosed list", encoding="utf-8")
    with pytest.raises(ConfigError, match="Error parsing YAML"):
        load_glossary(bad_yaml)


def test_invalid_glossary_structure(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("preservar: 12345", encoding="utf-8")
    with pytest.raises(ConfigError, match="Field 'preservar'"):
        load_glossary(bad_yaml)
