from .contexts import (
    build_client_report_context,
    build_internal_report_context,
    build_narrative_context,
    build_fallback_narrative,
    count_populated_context_fields,
    should_use_fallback_narrative,
)
from .models import (
    Assessment,
    ClientReportContext,
    Delivery,
    DeliveryStatus,
    InternalReportContext,
    Narrative,
    NarrativeContext,
    NormalizedApplication,
    PipelineStage,
    RawFormSubmission,
    Report,
    ReportType,
    StageError,
    SubmissionState,
    SubmissionStatus,
)
from .rules import FieldEqualsRule, RuleEngine, RuleEvaluation, RuleSet, StaticRuleEngine
from .state_machine import (
    failure_status_for_stage,
    is_failure_status,
    is_terminal_status,
    is_valid_transition,
    next_stage_for_status,
    stage_for_status,
)
from .validation import GenericNarrativeValidator, SemanticValidationFailure, ValidationOutcome

__all__ = [
    "Assessment",
    "ClientReportContext",
    "Delivery",
    "DeliveryStatus",
    "FieldEqualsRule",
    "GenericNarrativeValidator",
    "InternalReportContext",
    "Narrative",
    "NarrativeContext",
    "NormalizationError",
    "NormalizedApplication",
    "PipelineStage",
    "RawFormSubmission",
    "Report",
    "ReportType",
    "RuleEngine",
    "RuleEvaluation",
    "RuleSet",
    "SemanticValidationFailure",
    "StageError",
    "StaticRuleEngine",
    "SubmissionState",
    "SubmissionStatus",
    "ValidationOutcome",
    "build_client_report_context",
    "build_fallback_narrative",
    "build_internal_report_context",
    "build_narrative_context",
    "count_populated_context_fields",
    "failure_status_for_stage",
    "is_failure_status",
    "is_terminal_status",
    "is_valid_transition",
    "next_stage_for_status",
    "normalize_submission",
    "should_use_fallback_narrative",
    "stage_for_status",
]


def __getattr__(name: str):
    if name in {"NormalizationError", "normalize_submission"}:
        from .normalization import NormalizationError, normalize_submission

        exports = {
            "NormalizationError": NormalizationError,
            "normalize_submission": normalize_submission,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
