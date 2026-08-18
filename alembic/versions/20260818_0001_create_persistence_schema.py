"""create persistence schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260818_0001"
down_revision = None
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = (
    "raw_form_submissions",
    "normalized_applications",
    "assessments",
    "narratives",
    "reports",
    "deliveries",
)


def upgrade() -> None:
    op.create_table(
        "raw_form_submissions",
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("form_id", sa.String(length=255), nullable=False),
        sa.Column("response_id", sa.String(length=255), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("form_schema_version_at_receipt", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("submission_id"),
        sa.UniqueConstraint("form_id", "response_id", name="uq_raw_form_response"),
    )
    op.create_table(
        "normalized_applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("form_schema_version", sa.String(length=255), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalization_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_normalized_applications_submission_id"),
        "normalized_applications",
        ["submission_id"],
        unique=False,
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("rule_version", sa.String(length=255), nullable=False),
        sa.Column("rules_evaluated", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rules_triggered", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("qualification", sa.String(length=255), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assessments_submission_id"), "assessments", ["submission_id"], unique=False)
    op.create_table(
        "narratives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=255), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=False),
        sa.Column("validation_result", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("used_fallback", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_narratives_submission_id"), "narratives", ["submission_id"], unique=False)
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("template_version", sa.String(length=255), nullable=False),
        sa.Column("artifact_ref", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_submission_id"), "reports", ["submission_id"], unique=False)
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("delivery_key", sa.String(length=512), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deliveries_delivery_key"), "deliveries", ["delivery_key"], unique=False)
    op.create_index(op.f("ix_deliveries_submission_id"), "deliveries", ["submission_id"], unique=False)
    op.create_table(
        "submission_states",
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempt_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_error", postgresql.JSONB(astext_type=sa.Text(), none_as_null=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["raw_form_submissions.submission_id"]),
        sa.PrimaryKeyConstraint("submission_id"),
    )
    op.create_index(op.f("ix_submission_states_updated_at"), "submission_states", ["updated_at"], unique=False)

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION forbid_append_only_mutation()
            RETURNS trigger
            AS $$
            BEGIN
                RAISE EXCEPTION 'append-only table: % mutation is forbidden', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    for table_name in APPEND_ONLY_TABLES:
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {table_name}_append_only_guard
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW
                EXECUTE FUNCTION forbid_append_only_mutation();
                """
            )
        )


def downgrade() -> None:
    for table_name in APPEND_ONLY_TABLES:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {table_name}_append_only_guard ON {table_name}"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS forbid_append_only_mutation()"))
    op.drop_index(op.f("ix_submission_states_updated_at"), table_name="submission_states")
    op.drop_table("submission_states")
    op.drop_index(op.f("ix_deliveries_submission_id"), table_name="deliveries")
    op.drop_index(op.f("ix_deliveries_delivery_key"), table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_index(op.f("ix_reports_submission_id"), table_name="reports")
    op.drop_table("reports")
    op.drop_index(op.f("ix_narratives_submission_id"), table_name="narratives")
    op.drop_table("narratives")
    op.drop_index(op.f("ix_assessments_submission_id"), table_name="assessments")
    op.drop_table("assessments")
    op.drop_index(op.f("ix_normalized_applications_submission_id"), table_name="normalized_applications")
    op.drop_table("normalized_applications")
    op.drop_table("raw_form_submissions")
