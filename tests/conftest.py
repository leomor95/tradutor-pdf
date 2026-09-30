import os
from collections.abc import Callable
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeOllamaClient:
    """Fake Ollama client for unit testing without calling real LLM."""

    def __init__(
        self,
        default_response: str = "Texto traduzido pelo modelo de teste.",
        default_model: str = "qwen2.5:7b-instruct-q4_K_M",
    ) -> None:
        self.default_model = default_model
        self.default_response = default_response
        self.responses: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.custom_handler: Callable[[str], str] | None = None
        self.device: str = "CUDA"
        self.should_fail: Exception | None = None
        self.is_healthy: bool = True

    def set_response(self, text: str) -> None:
        """Set a single response for subsequent calls."""
        self.default_response = text

    def queue_responses(self, *texts: str) -> None:
        """Queue multiple sequential responses."""
        self.responses.extend(texts)

    def health_check(self, model: str | None = None) -> bool:
        return self.is_healthy

    def list_models(self) -> list[str]:
        return [self.default_model]

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> str:
        if self.should_fail:
            raise self.should_fail

        call_record = {
            "prompt": prompt,
            "model": model or self.default_model,
            "system": system,
            "temperature": temperature,
            "options": options or {},
        }
        self.calls.append(call_record)

        if self.custom_handler:
            return self.custom_handler(prompt)

        if self.responses:
            return self.responses.pop(0)

        return self.default_response

    def detect_device(self, log_result: bool = True) -> str:
        return self.device


@pytest.fixture
def fake_llm() -> FakeOllamaClient:
    """Fixture providing a controllable fake Ollama client."""
    return FakeOllamaClient()


@pytest.fixture(autouse=True)
def isolate_test_cache(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure every test has its own isolated cache directory."""
    cache_dir = tmp_path_factory.mktemp("test_env") / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TRADUTOR_CACHE_DIR", str(cache_dir))
