from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sqlalchemy_imports_stay_inside_postgres_package() -> None:
    script = """
import ast
from pathlib import Path

root = Path.cwd() / "src"
violations = []
for path in root.rglob("*.py"):
    if "src/persistence/postgres/" in path.as_posix():
        continue
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            if any(name == "sqlalchemy" or name.startswith("sqlalchemy.") for name in names):
                violations.append(path.as_posix())
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "sqlalchemy" or module.startswith("sqlalchemy."):
                violations.append(path.as_posix())
if violations:
    raise SystemExit("\\n".join(sorted(set(violations))))
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"


def test_docker_compose_uses_only_synthetic_local_credentials() -> None:
    compose_text = (ROOT / "docker-compose.yml").read_text()

    assert "local_test_user" in compose_text
    assert "local_test_password" in compose_text
    assert "google_forms_reports_test" in compose_text

    forbidden_patterns = [
        r"secretmanager",
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"AKIA[0-9A-Z]{16}",
        r"ya29\.[0-9A-Za-z\-_]+",
        r"postgresql\+psycopg://[^\\n]+@postgres",
        r"quiron",
        r"prod",
        r"gmail",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, compose_text, flags=re.IGNORECASE) is None, pattern
