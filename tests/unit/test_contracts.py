from datetime import datetime

from src.adapters.gmail import FakeEmailSender
from src.adapters.llm import NullLLMProvider
from src.adapters.pdf import FakeReportRenderer
from src.config.models import LLMProviderConfig, PromptTemplate, ReportTemplate
from src.domain.models import ClientReportContext, NarrativeContext, Report, ReportType
from src.persistence import InMemoryRepositories


def test_null_llm_provider_contract() -> None:
    provider = NullLLMProvider()
    generation = provider.generate_narrative(
        context=NarrativeContext(
            submission_id="submission-1",
            applicant_fields={"applicant_name": "test-applicant-001"},
            reasons=("Synthetic reason",),
            qualification="REVIEW",
            rule_version="rules-v1",
        ),
        prompt_template=PromptTemplate(
            version="prompt-v1",
            approved_for_production=False,
            template_text="Draft prompt",
        ),
        provider_config=LLMProviderConfig(
            version="llm-v1",
            provider_name="null-llm",
            model_name="template-only",
            prompt_version="prompt-v1",
            approved_for_production=False,
        ),
    )

    assert generation.provider == "null-llm"
    assert "Qualification: REVIEW" in generation.text


def test_fake_report_renderer_contract() -> None:
    renderer = FakeReportRenderer()
    artifact = renderer.render(
        context=ClientReportContext(
            submission_id="submission-1",
            allowed_fields={},
            narrative_text="Qualification: REVIEW",
            qualification_label="REVIEW",
        ),
        template=ReportTemplate(
            version="template-v1",
            report_type=ReportType.CLIENT,
            approved_for_production=False,
            template_text="Draft client template",
        ),
    )

    assert artifact.artifact_ref == "submission-1-client-template-v1"
    assert artifact.content.startswith(b"CLIENT:")


def test_fake_email_sender_contract_is_idempotent_by_delivery_key() -> None:
    sender = FakeEmailSender(now_factory=lambda: datetime(2026, 8, 18))
    report = Report(
        submission_id="submission-1",
        report_type=ReportType.CLIENT,
        template_version="template-v1",
        artifact_ref="artifact-1",
        content=b"client",
        generated_at=datetime(2026, 8, 18),
    )

    first = sender.send(report=report, recipient="client@example.invalid", delivery_key="key-1")
    second = sender.send(report=report, recipient="client@example.invalid", delivery_key="key-1")

    assert first == second


def test_in_memory_repositories_contract() -> None:
    repositories = InMemoryRepositories()

    assert not hasattr(repositories.raw_submissions, "update")
