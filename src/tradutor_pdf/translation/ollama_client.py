from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from tradutor_pdf.config import find_project_root

logger = logging.getLogger("tradutor_pdf.ollama")


class OllamaError(Exception):
    """Base exception for Ollama client errors."""


class OllamaConnectionError(OllamaError):
    """Raised when unable to connect to Ollama server."""


class OllamaModelNotFoundError(OllamaError):
    """Raised when the requested model is not found in Ollama."""


class OllamaClient:
    """Minimal HTTP client for interacting with the local Ollama server."""

    def __init__(
        self,
        host: str | None = None,
        default_model: str = "qwen2.5:7b-instruct-q4_K_M",
        timeout: float = 60.0,
    ) -> None:
        raw_host = host or os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
        if not raw_host.startswith("http://") and not raw_host.startswith("https://"):
            self.base_url = f"http://{raw_host}"
        else:
            self.base_url = raw_host.rstrip("/")

        self.default_model = default_model
        self.timeout = timeout

    def health_check(self, model: str | None = None) -> bool:
        """Check if Ollama server is running and optionally verify if model is available."""
        target_model = model or self.default_model
        try:
            with httpx.Client(base_url=self.base_url, timeout=5.0) as client:
                resp = client.get("/api/tags")
                if resp.status_code != 200:
                    return False
                if target_model:
                    data = resp.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    # Check exact match or base tag match
                    return any(
                        m == target_model
                        or (m and m.split(":")[0] == target_model.split(":")[0])
                        for m in models
                    )
                return True
        except (httpx.RequestError, httpx.HTTPError) as exc:
            logger.debug("Ollama health check request failed: %s", exc)
            return False

    def list_models(self) -> list[str]:
        """Return list of available model names installed locally."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                resp = client.get("/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", []) if "name" in m]
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {self.base_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise OllamaError(f"Error listing models: {exc}") from exc

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Generate text completion from Ollama."""
        target_model = model or self.default_model
        req_options: dict[str, Any] = {"temperature": temperature}
        if options:
            req_options.update(options)

        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": req_options,
        }
        if system:
            payload["system"] = system

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.post("/api/generate", json=payload)
                if resp.status_code == 404:
                    raise OllamaModelNotFoundError(
                        f"Model '{target_model}' not found in Ollama at {self.base_url}"
                    )
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("response", ""))
        except (OllamaModelNotFoundError, OllamaConnectionError):
            raise
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Request error when calling Ollama at {self.base_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise OllamaError(f"Ollama generation failed: {exc}") from exc

    def detect_device(self, log_result: bool = True) -> str:
        """Detect whether Ollama is executing models on CUDA (GPU) or CPU and log it."""
        device = "CPU"
        details = ""

        # Method 1: Check running models in /api/ps
        models_checked = False
        try:
            with httpx.Client(base_url=self.base_url, timeout=5.0) as client:
                resp = client.get("/api/ps")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    if models:
                        models_checked = True
                        for m in models:
                            size_vram = m.get("size_vram", 0)
                            if size_vram and size_vram > 0:
                                device = "CUDA"
                                details = f"model '{m.get('name')}' active in VRAM ({size_vram // (1024 * 1024)} MiB)"
                                break
                        if device != "CUDA":
                            device = "CPU"
                            details = "model loaded with 0 VRAM allocation"
        except (httpx.RequestError, httpx.HTTPError) as exc:
            logger.debug("Could not query Ollama /api/ps: %s", exc)

        # Method 2: Inspect recent lines of logs/ollama.log only if no model was in /api/ps
        if not models_checked:
            log_path = find_project_root() / "logs" / "ollama.log"
            if log_path.is_file():
                try:
                    content = log_path.read_text(encoding="utf-8", errors="ignore")
                    if "library=CUDA" in content or "using device CUDA" in content:
                        device = "CUDA"
                        details = "CUDA device initialization found in ollama.log"
                except OSError as exc:
                    logger.debug("Could not read logs/ollama.log: %s", exc)

        if log_result:
            if device == "CUDA":
                logger.info(
                    "Ollama execution device detected: CUDA (GPU) - %s",
                    details or "GPU compute enabled",
                )
            else:
                logger.warning(
                    "Ollama execution device detected: CPU (GPU acceleration not active)"
                )

        return device


def check_service_health(
    host: str | None = None,
    model: str | None = None,
) -> tuple[bool, str]:
    """Check Ollama service status and model presence.

    Returns:
        (True, "") if healthy.
        (False, actionable_error_message) if Ollama is not running or model is missing.
    """
    client = OllamaClient(host=host, default_model=model or "")
    try:
        models = client.list_models()
    except (OllamaConnectionError, httpx.RequestError):
        return False, (
            "O serviço de tradução local (Ollama) não está em execução. "
            "Execute `./scripts/run.sh` no terminal para iniciar o serviço."
        )
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Não foi possível conectar ao Ollama ({exc}). "
            "Verifique se o serviço local está ativo via `./scripts/run.sh`."
        )

    if model:
        has_model = any(
            m == model or (m and m.split(":")[0] == model.split(":")[0]) for m in models
        )
        if not has_model:
            return False, (
                f"O modelo '{model}' não está instalado no Ollama local. "
                "Execute `./scripts/setup.sh` no terminal para baixar o modelo configurado."
            )

    return True, ""
