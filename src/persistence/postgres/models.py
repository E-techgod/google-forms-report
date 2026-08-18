from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawFormSubmissionRow(Base):
    __tablename__ = "raw_form_submissions"
    __table_args__ = (UniqueConstraint("form_id", "response_id", name="uq_raw_form_response"),)

    submission_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    form_id: Mapped[str] = mapped_column(String(255), nullable=False)
    response_id: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    form_schema_version_at_receipt: Mapped[str] = mapped_column(String(255), nullable=False)


class NormalizedApplicationRow(Base):
    __tablename__ = "normalized_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        nullable=False,
        index=True,
    )
    form_schema_version: Mapped[str] = mapped_column(String(255), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalization_warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class AssessmentRow(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        nullable=False,
        index=True,
    )
    rule_version: Mapped[str] = mapped_column(String(255), nullable=False)
    rules_evaluated: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rules_triggered: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    qualification: Mapped[str] = mapped_column(String(255), nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class NarrativeRow(Base):
    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)
    validation_result: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_fallback: Mapped[bool] = mapped_column(nullable=False, default=False)


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class DeliveryRow(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    delivery_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SubmissionStateRow(Base):
    __tablename__ = "submission_states"

    submission_id: Mapped[str] = mapped_column(
        ForeignKey("raw_form_submissions.submission_id"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
