from __future__ import annotations

"""Run locally with: docker compose up -d postgres && uv run --group dev pytest tests/contract -q."""

import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_URL = "postgresql+psycopg://local_test_user:local_test_password@127.0.0.1:54329/google_forms_reports_test"
TRUNCATE_TABLES = (
    "submission_states",
    "deliveries",
    "reports",
    "narratives",
    "assessments",
    "normalized_applications",
    "raw_form_submissions",
)


def _psycopg_dsn(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    return os.environ.get("POSTGRES_TEST_DATABASE_URL", DEFAULT_DB_URL)


@pytest.fixture(scope="session")
def migrated_postgres(postgres_database_url: str) -> str:
    import psycopg

    dsn = _psycopg_dsn(postgres_database_url)
    with psycopg.connect(dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("CREATE SCHEMA public")
    env = os.environ | {"ALEMBIC_DATABASE_URL": postgres_database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return postgres_database_url


@pytest.fixture()
def postgres_repositories(migrated_postgres: str):
    import psycopg
    from src.persistence.postgres import PostgresRepositories

    dsn = _psycopg_dsn(migrated_postgres)
    with psycopg.connect(dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE")
    repositories = PostgresRepositories(migrated_postgres)
    try:
        yield repositories
    finally:
        repositories.dispose()


@pytest.fixture()
def postgres_dsn(migrated_postgres: str) -> str:
    return _psycopg_dsn(migrated_postgres)
