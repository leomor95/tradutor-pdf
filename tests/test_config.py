from pathlib import Path

import pytest

from tradutor_pdf.config import (
    ConfigError,
    Settings,
    find_project_root,
    get_default_destination,
    get_last_destination,
    get_user_state_path,
    load_glossary,
    load_settings,
    save_last_destination,
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


def test_user_state_path_location() -> None:
    path = get_user_state_path()
    root = find_project_root()
    assert str(path).startswith(str(root / "config"))
    assert path.name == "state.json"
    assert "~/.config" not in str(path)


def test_get_last_destination_empty(tmp_path: Path) -> None:
    state_file = tmp_path / "empty_state.json"
    assert get_last_destination(state_file) is None


def test_save_and_get_last_destination(tmp_path: Path) -> None:
    state_file = tmp_path / "config" / "state.json"
    target = tmp_path / "my_output"
    target.mkdir()

    save_last_destination(target, state_path=state_file)
    assert state_file.is_file()

    loaded = get_last_destination(state_path=state_file)
    assert loaded == target.resolve()


def test_get_default_destination_fallback(tmp_path: Path) -> None:
    state_file = tmp_path / "nonexistent.json"
    default_dest = get_default_destination(state_path=state_file)
    settings = load_settings()
    assert default_dest == settings.output.resolved_dir


def test_get_default_destination_uses_last(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    custom_dest = tmp_path / "custom_translations"
    custom_dest.mkdir()
    save_last_destination(custom_dest, state_path=state_file)

    default_dest = get_default_destination(state_path=state_file)
    assert default_dest == custom_dest.resolve()
