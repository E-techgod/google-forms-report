from __future__ import annotations

import subprocess
import sys


def test_src_config_is_importable_before_src_domain() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from src.config import AppConfig; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
