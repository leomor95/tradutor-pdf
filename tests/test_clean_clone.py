from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tradutor_pdf.config import find_project_root


@pytest.mark.slow
def test_clean_clone_setup_and_run_check(tmp_path: Path) -> None:
    """Verify CA14 / RNF25: Clean clone setup.sh and run.sh --check work out of the box."""
    root = find_project_root()
    clone_dir = tmp_path / "clone_test"

    # 1. Clone repository
    res_clone = subprocess.run(
        ["git", "clone", str(root), str(clone_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_clone.returncode == 0, f"git clone failed: {res_clone.stderr}"

    # 2. Copy docs/ (which is in .gitignore)
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        shutil.copytree(docs_dir, clone_dir / "docs")

    # Link/copy bin, lib and models to avoid multi-gigabyte re-downloading during test
    if (root / "bin").is_dir():
        os.system(f"cp -al '{root}/bin' '{clone_dir}/bin'")
    if (root / "lib").is_dir():
        os.system(f"cp -al '{root}/lib' '{clone_dir}/lib'")
    if (root / "models").is_dir():
        os.system(f"cp -al '{root}/models' '{clone_dir}/models'")

    # 3. Execute setup.sh
    res_setup = subprocess.run(
        ["./scripts/setup.sh"],
        cwd=str(clone_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_setup.returncode == 0, (
        f"setup.sh failed in clean clone:\nSTDOUT:\n{res_setup.stdout}\nSTDERR:\n{res_setup.stderr}"
    )

    # 4. Execute run.sh --check
    try:
        res_check = subprocess.run(
            ["./scripts/run.sh", "--check"],
            cwd=str(clone_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_check.returncode == 0, (
            f"run.sh --check failed in clean clone:\nSTDOUT:\n{res_check.stdout}\nSTDERR:\n{res_check.stderr}"
        )
        assert "respondeu com sucesso" in res_check.stdout
    finally:
        # Clean up clone's Ollama server
        subprocess.run(["pkill", "-f", str(clone_dir)], check=False)
