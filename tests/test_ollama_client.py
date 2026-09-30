from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.conftest import FakeOllamaClient
from tradutor_pdf.translation.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
)


def test_fake_llm_fixture(fake_llm: FakeOllamaClient) -> None:
    assert fake_llm.health_check() is True
    assert fake_llm.list_models() == ["qwen2.5:7b-instruct-q4_K_M"]
    assert fake_llm.detect_device() == "CUDA"

    response = fake_llm.generate("Hello world")
    assert response == "Texto traduzido pelo modelo de teste."
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["prompt"] == "Hello world"

    fake_llm.queue_responses("Primeira", "Segunda")
    assert fake_llm.generate("p1") == "Primeira"
    assert fake_llm.generate("p2") == "Segunda"


def test_fake_llm_error_simulation(fake_llm: FakeOllamaClient) -> None:
    fake_llm.should_fail = OllamaConnectionError("Connection refused")
    with pytest.raises(OllamaConnectionError, match="Connection refused"):
        fake_llm.generate("test")


def test_ollama_client_health_check_success() -> None:
    client = OllamaClient(host="http://localhost:11434", default_model="model_a")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "model_a:latest"}]}

    with patch("httpx.Client.get", return_value=mock_resp):
        assert client.health_check("model_a") is True
        assert client.health_check("model_b") is False


def test_ollama_client_health_check_failure() -> None:
    client = OllamaClient(host="http://localhost:11434")
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("network down")):
        assert client.health_check() is False


def test_ollama_client_generate_success() -> None:
    client = OllamaClient(host="http://localhost:11434", default_model="test_model")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "Olá mundo"}

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.generate("Hello world", temperature=0.3)
        assert res == "Olá mundo"


def test_ollama_client_generate_404_model_not_found() -> None:
    client = OllamaClient(host="http://localhost:11434", default_model="non_existent")
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with (
        patch("httpx.Client.post", return_value=mock_resp),
        pytest.raises(OllamaModelNotFoundError, match="Model 'non_existent' not found"),
    ):
        client.generate("Hello")


def test_ollama_client_detect_device_cuda() -> None:
    client = OllamaClient(host="http://localhost:11434")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:7b-instruct-q4_K_M", "size_vram": 4748056984}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        device = client.detect_device(log_result=False)
        assert device == "CUDA"


def test_ollama_client_detect_device_cpu() -> None:
    client = OllamaClient(host="http://localhost:11434")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:7b-instruct-q4_K_M", "size_vram": 0}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        device = client.detect_device(log_result=False)
        assert device == "CPU"


@pytest.mark.slow
def test_real_ollama_connection() -> None:
    client = OllamaClient()
    assert client.health_check() is True
    resp = client.generate("Responda apenas 'OK'.")
    assert "OK" in resp.upper()
