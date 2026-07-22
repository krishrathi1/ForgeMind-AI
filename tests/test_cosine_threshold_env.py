"""Empty COSINE_THRESHOLD must not crash ForgeMind class construction.

``cosine_better_than_threshold`` previously used bare ``float(os.getenv(...))``,
which raises ``ValueError`` when the variable is present but empty (common in
``.env`` / Docker Compose). Sibling knobs already go through ``get_env_value``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.offline
@pytest.mark.parametrize("env_value", ["", "  ", "\t"])
def test_empty_cosine_threshold_env_falls_back_on_import(env_value: str) -> None:
    env = os.environ.copy()
    env["COSINE_THRESHOLD"] = env_value
    env["PYTHONPATH"] = str(REPO_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from forgemind.forgemind import ForgeMind; "
            "print(ForgeMind.__dataclass_fields__"
            "['cosine_better_than_threshold'].default)",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.2"
