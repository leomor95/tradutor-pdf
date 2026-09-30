from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tradutor_pdf.config import find_project_root


@pytest.mark.slow
def test_complete_offline_translation(tmp_path: Path) -> None:
    """Verify CA08/RNF01/RNF02: Document translation operates with zero external network connectivity."""
    root = find_project_root()
    simple_pdf = root / "tests" / "fixtures" / "simple.pdf"
    assert simple_pdf.is_file(), f"Fixture {simple_pdf} not found"

    unshare_bin = shutil.which("unshare")
    if not unshare_bin:
        pytest.skip("unshare not available on this platform")

    # Terminate any host Ollama process to ensure full VRAM is available for isolated Ollama
    subprocess.run(["pkill", "-f", "bin/ollama"], check=False)
    subprocess.run(["pkill", "-f", "llama-server"], check=False)

    out_file = tmp_path / "offline_result.md"

    # Script executed inside isolated network namespace with loopback enabled but no external routing
    script = f"""
set -euo pipefail
ip link set lo up

export ROOT_DIR="{root}"
export OLLAMA_MODELS="$ROOT_DIR/models"
export OLLAMA_HOST="127.0.0.1:11436"
export XDG_CACHE_HOME="$ROOT_DIR/.cache"
export HF_HOME="$ROOT_DIR/.cache/hf"
export UV_CACHE_DIR="$ROOT_DIR/.cache/uv"
export TMPDIR="$ROOT_DIR/.cache/tmp"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# Verify that external network is completely blocked
if curl --connect-timeout 1 -s https://1.1.1.1 >/dev/null 2>&1; then
    echo "Network leak: external internet is reachable!" >&2
    exit 1
fi

# Start isolated local Ollama on loopback
"$ROOT_DIR/bin/ollama" serve >/dev/null 2>&1 &
OLLAMA_PID=$!
trap 'kill $OLLAMA_PID 2>/dev/null || true' EXIT

TRIES=0
until curl -s "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; do
    sleep 0.3
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 40 ]; then
        echo "Failed to start isolated Ollama" >&2
        exit 1
    fi
done

# Run CLI translation
uv run python -m tradutor_pdf --cli "{simple_pdf}" -o "{out_file}" --restart
"""

    try:
        res = subprocess.run(
            [unshare_bin, "-r", "-n", "bash", "-c", script],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )

        assert res.returncode == 0, (
            f"Offline translation failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        assert out_file.is_file(), "Output markdown file was not generated"
        content = out_file.read_text(encoding="utf-8")
        assert len(content) > 50
        assert "<!-- NÃO TRADUZIDO -->" not in content
    finally:
        # Restore host Ollama for subsequent tests
        subprocess.run([str(root / "scripts" / "run.sh"), "--check"], check=False)
