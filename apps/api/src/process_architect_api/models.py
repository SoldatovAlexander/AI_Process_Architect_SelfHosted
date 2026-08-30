from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .localization import normalize_locale


class ProcessDescriptionRequest(BaseModel):
    description: str = Field(min_length=20, max_length=20_000)


class ValidationIssue(BaseModel):
    severity: str
    code: str
    message: str
    path: str


class ValidationCounts(BaseModel):
    errors: int
    warnings: int


class ValidationResult(BaseModel):
    valid: bool
    counts: ValidationCounts
    issues: list[ValidationIssue]


class ProcessDraftResponse(BaseModel):
    process_ir: dict[str, Any]
    validation: ValidationResult
    provider: str
    model: str


class ProjectCreateRequest(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    default_locale: str | None = Field(default=None, min_length=2, max_length=35)
    process_ir: dict[str, Any]
    target_mode: Literal["process", "agent"] = "process"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank.")
        return value

    @field_validator("default_locale")
    @classmethod
    def validate_default_locale(cls, value: str | None) -> str | None:
        return normalize_locale(value) if value else None


class ProcessTemplateResponse(BaseModel):
    id: str
    category: str
    category_name: str
    name: str
    description: str
    step_count: int
    actor_count: int
    system_count: int
    preview_steps: list[str]
    process_ir: dict[str, Any] | None = None
    status: Literal["ready", "interview_draft"] = "ready"
    priority: str | None = None
    ai_required: bool | None = None
    human_in_loop: bool | None = None
    automation_pattern: str | None = None
    source_template_id: int | None = None
    source_url: str | None = None
    library_number: int | None = None
    agent_enabled: bool = False
    agent_topology: str | None = None
    search_terms: list[str] = Field(default_factory=list)
    rubric_entry_ids: list[str] = Field(default_factory=list)
    source: Literal["catalog", "user"] = "catalog"
    collection_ids: list[str] = Field(default_factory=list)
    favorite: bool = False


class ProcessTemplateSuggestionRequest(BaseModel):
    text: str = Field(min_length=3, max_length=100_000)
    locale: str = Field(default="ru", min_length=2, max_length=35)
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)
    rubric_entry_ids: list[str] = Field(default_factory=list, max_length=9)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        return normalize_locale(value)


class ProcessTemplateSuggestionResponse(BaseModel):
    template: ProcessTemplateResponse
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_signals: list[str] = Field(default_factory=list)


class ProcessTemplateApplyRequest(BaseModel):
    base_revision_id: str
    locale: str = Field(default="ru", min_length=2, max_length=35)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        return normalize_locale(value)


class TemplateCollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value.strip()


class TemplateCollectionItemRequest(BaseModel):
    template_source: Literal["catalog", "user"]
    template_id: str = Field(min_length=1, max_length=160)


class TemplateCollectionResponse(BaseModel):
    id: str
    name: str
    is_favorites: bool
    item_count: int
    created_at: datetime


class TemplateCollectionItemResponse(BaseModel):
    collection_id: str
    template_source: Literal["catalog", "user"]
    template_id: str


class UserTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    collection_ids: list[str] = Field(default_factory=list, max_length=50)
    favorite: bool = False

    @field_validator("name")
    @classmethod
    def validate_template_name(cls, value: str) -> str:
        return value.strip()


class N8nImportRequest(BaseModel):
    workspace_id: str
    workflow: dict[str, Any]
    source_minor: Literal["2.32", "2.31", "2.30"] | None = None
    locale: str = Field(default="ru", min_length=2, max_length=35)

    @field_validator("locale")
    @classmethod
    def validate_import_locale(cls, value: str) -> str:
        return normalize_locale(value)


class N8nImportDiagnosticsResponse(BaseModel):
    status: str
    nodeCount: int
    connectionCount: int
    knownNodeCount: int
    unknownNodes: list[dict[str, str]]
    danglingConnections: list[dict[str, str]]
    credentialReferences: list[dict[str, Any]]
    warnings: list[str]


class N8nImportResponse(BaseModel):
    project: "ProjectResponse"
    artifact_id: str
    source_minor: str
    source_sha256: str
    diagnostics: N8nImportDiagnosticsResponse


class N8nImportArtifactResponse(BaseModel):
    id: str
    project_id: str
    revision_id: str
    source_minor: str
    workflow_name: str
    source_sha256: str
    source_workflow: dict[str, Any]
    diagnostics: N8nImportDiagnosticsResponse
    created_at: datetime


class N8nRoundtripRequest(BaseModel):
    revision_id: str
    locale: str = Field(default="en", min_length=2, max_length=35)
    include_general_guide: bool = True

    @field_validator("locale")
    @classmethod
    def validate_roundtrip_locale(cls, value: str) -> str:
        return normalize_locale(value)


class PythonCodeValidationRequest(BaseModel):
    process_ir: dict[str, Any]
    step_id: str = Field(min_length=1, max_length=200)
    target_minor: Literal["2.32", "2.31", "2.30"] = "2.32"
    custom_logic: dict[str, Any]


class PythonCodeGenerationRequest(BaseModel):
    process_ir: dict[str, Any]
    step_id: str = Field(min_length=1, max_length=200)
    business_rule_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    input_field: str = Field(min_length=1, max_length=200)
    output_field: str = Field(min_length=1, max_length=200)
    operator: Literal["<", "<=", "==", "!=", ">=", ">"]
    threshold: float


class PythonCodeValidationResponse(BaseModel):
    valid: bool
    artifact: dict[str, Any]
    checks: dict[str, Literal["passed", "failed"]]
    errors: list[dict[str, str]]
    execution: dict[str, Any] | None = None


class ProcessRevisionResponse(BaseModel):
    id: str
    project_id: str
    version_number: int
    schema_version: str
    process_ir: dict[str, Any]
    forward_patch: list[dict[str, Any]] | None
    inverse_patch: list[dict[str, Any]] | None
    validation: ValidationResult
    parent_revision_id: str | None
    restored_from_revision_id: str | None
    source: str
    perspective: Literal["as_is", "to_be"] = "to_be"
    created_by_user_id: str
    created_at: datetime


class ProjectResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    default_locale: str
    status: str
    target_mode: Literal["process", "agent"] = "process"
    current_revision_id: str
    current_revision: ProcessRevisionResponse
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class ProjectArchiveValidationResponse(BaseModel):
    valid: bool
    archive_sha256: str
    source_project_id: str
    project_name: str
    format_version: str
    counts: dict[str, int]
    warnings: list[str]
    already_restored_project_id: str | None = None


class ProjectArchiveRestoreResponse(BaseModel):
    project: ProjectResponse
    archive_sha256: str
    already_restored: bool


class ProjectPatchRequest(BaseModel):
    base_revision_id: str
    patch: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class ProjectTargetModeRequest(BaseModel):
    target_mode: Literal["process", "agent"]


class RubricEntryResponse(BaseModel):
    id: str
    code: str
    parent_id: str | None
    name: str
    description: str
    synonyms: list[str]
    deprecated: bool


class RubricDimensionResponse(BaseModel):
    id: str
    name: str
    entries: list[RubricEntryResponse]


class RubricResponse(BaseModel):
    version: str
    status: str
    dimensions: list[RubricDimensionResponse]


class ProjectClassificationRequest(BaseModel):
    base_revision_id: str
    rubric_version: str
    entry_ids: list[str] = Field(min_length=1, max_length=20)


class ProjectUndoRequest(BaseModel):
    base_revision_id: str


class ProjectRestoreRequest(BaseModel):
    base_revision_id: str
    target_revision_id: str


class RevisionDiffResponse(BaseModel):
    project_id: str
    from_revision_id: str
    to_revision_id: str
    patch: list[dict[str, Any]]


class ReadinessCategoryResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["ok", "warning", "blocked"]
    reason_codes: list[str]


class AgentReadinessResponse(BaseModel):
    scope: Literal["agent_deployment"] = "agent_deployment"
    overall: int = Field(ge=0, le=100)
    agentReady: bool
    blockers: list[str]
    blockingQuestionCount: int
    categories: dict[str, ReadinessCategoryResponse]


class AgentRunLimits(BaseModel):
    max_steps: int = Field(default=20, ge=1, le=200)
    max_tool_calls: int = Field(default=10, ge=0, le=100)
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    max_cost_microunits: int = Field(default=0, ge=0, le=1_000_000_000)


class RuntimeConnectionProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    kind: Literal["n8n", "openclaw", "hermes"]
    endpoint_url: str = Field(min_length=8, max_length=2_000)
    secret_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{2,127}$")
    n8n_minor: Literal["2.32", "2.31", "2.30"] | None = None

    @field_validator("name", "endpoint_url")
    @classmethod
    def trim_runtime_profile_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_runtime_version(self):
        if (self.kind == "n8n") != (self.n8n_minor is not None):
            raise ValueError("n8n_minor is required only for n8n profiles.")
        return self


class RuntimeConnectionProfileResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    kind: Literal["n8n", "openclaw", "hermes"]
    endpoint_url: str
    secret_ref: str
    n8n_minor: Literal["2.32", "2.31", "2.30"] | None
    status: Literal["draft", "verified", "failed", "disabled"]
    detected_version: str | None
    last_check_code: str | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RuntimeConnectionCheckResponse(BaseModel):
    profile: RuntimeConnectionProfileResponse
    result_code: str
    detected_version: str | None


class N8nPublicationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    revision_id: str


class N8nPublicationCreateRequest(N8nPublicationPreviewRequest):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_workflow_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class N8nPublicationPreviewResponse(BaseModel):
    profile_id: str
    revision_id: str
    target_minor: Literal["2.32", "2.31", "2.30"]
    workflow_name: str
    workflow_sha256: str
    node_count: int
    connection_count: int
    active: Literal[False] = False
    source_mode: Literal["generated", "round_trip"]


class N8nPublicationResponse(BaseModel):
    id: str
    project_id: str
    revision_id: str
    profile_id: str
    workflow_sha256: str
    remote_workflow_id: str | None
    status: Literal["publishing", "published", "failed", "deleted", "deletion_failed"]
    last_error_code: str | None
    created_at: datetime
    published_at: datetime | None
    deleted_at: datetime | None


class AgentPackageDeliveryPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    revision_id: str


class AgentPackageDeliveryCreateRequest(AgentPackageDeliveryPreviewRequest):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentPackageDeliveryPreviewResponse(BaseModel):
    profile_id: str
    revision_id: str
    runtime: Literal["openclaw", "hermes"]
    process_name: str
    package_sha256: str
    package_size: int
    file_count: int
    readiness_score: int
    blocker_count: int
    ready: bool
    active: Literal[False] = False


class AgentPackageDeliveryResponse(BaseModel):
    id: str
    project_id: str
    revision_id: str
    profile_id: str
    runtime: Literal["openclaw", "hermes"]
    package_sha256: str
    package_size: int
    file_count: int
    remote_package_id: str | None
    status: Literal["storing", "stored", "failed", "deleted", "deletion_failed"]
    last_error_code: str | None
    created_at: datetime
    stored_at: datetime | None
    deleted_at: datetime | None


class AgentRunCreateRequest(BaseModel):
    runtime: Literal["openclaw", "hermes"]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    limits: AgentRunLimits = Field(default_factory=AgentRunLimits)


class AgentRunDispatchRequest(AgentRunCreateRequest):
    pass


class AgentDispatchJobResponse(BaseModel):
    id: str
    run_id: str
    status: Literal["queued", "leased", "retry_wait", "dispatched", "dead_letter", "cancelled"]
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error_code: str | None
    dispatched_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentRunEventResponse(BaseModel):
    id: str
    sequence: int
    event_type: str
    actor_type: Literal["user", "system", "agent"]
    reason_code: str | None
    metrics: dict[str, int | float | bool]
    created_at: datetime


class AgentRunResponse(BaseModel):
    id: str
    project_id: str
    revision_id: str
    runtime: Literal["openclaw", "hermes"]
    status: Literal["created", "running", "awaiting_approval", "completed", "failed", "escalated", "cancelled"]
    contract_version: str
    idempotency_key: str
    limits: AgentRunLimits
    usage: dict[str, int]
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[AgentRunEventResponse]
    dispatch_status: Literal["queued", "leased", "retry_wait", "dispatched", "dead_letter", "cancelled"] | None = None
    dispatch_attempts: int = 0
    incident_id: str | None = None
    incident_status: Literal["open", "resolved", "replayed"] | None = None
    incident_category: Literal["dispatch", "runtime", "limit", "timeout", "escalation"] | None = None
    incident_reason_code: str | None = None
    replay_run_id: str | None = None


class AgentDispatchResponse(BaseModel):
    run: AgentRunResponse
    job: AgentDispatchJobResponse


class AgentIncidentResponse(BaseModel):
    id: str
    project_id: str
    run_id: str
    status: Literal["open", "resolved", "replayed"]
    category: Literal["dispatch", "runtime", "limit", "timeout", "escalation"]
    reason_code: str
    resolution_code: str | None
    replay_run_id: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentIncidentResolveRequest(BaseModel):
    resolution_code: Literal["reviewed_no_retry", "accepted_escalation"]


class AgentIncidentReplayRequest(BaseModel):
    revision: Literal["original", "current"]
    resolution_code: Literal["reviewed_retry", "configuration_fixed", "permissions_updated", "process_revised"]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class AgentIncidentReplayResponse(BaseModel):
    incident: AgentIncidentResponse
    dispatch: AgentDispatchResponse


class AgentRunTransitionRequest(BaseModel):
    action: Literal["start", "request_approval", "approve", "complete", "fail", "escalate", "cancel"]
    reason_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")


class AgentRunUsageRequest(BaseModel):
    steps: int = Field(default=0, ge=0, le=200)
    tool_calls: int = Field(default=0, ge=0, le=100)
    cost_microunits: int = Field(default=0, ge=0, le=1_000_000_000)


class AgentRuntimeCallbackRequest(BaseModel):
    model_config = {"extra": "forbid"}
    callback_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    status: Literal["awaiting_approval", "completed", "failed", "escalated"]
    reason_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")
    steps: int = Field(default=0, ge=0, le=200)
    tool_calls: int = Field(default=0, ge=0, le=100)
    cost_microunits: int = Field(default=0, ge=0, le=1_000_000_000)


class AgentEvaluationResultRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_:-]+$")
    passed: bool
    reason_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")


class AgentEvaluationCreateRequest(BaseModel):
    runtime: Literal["openclaw", "hermes"]
    results: list[AgentEvaluationResultRequest] = Field(min_length=1, max_length=200)
    cost_microunits: int = Field(default=0, ge=0, le=1_000_000_000)
    duration_ms: int = Field(default=0, ge=0, le=86_400_000)


class AgentEvaluationRunResponse(BaseModel):
    id: str
    project_id: str
    revision_id: str
    runtime: Literal["openclaw", "hermes"]
    suite_version: str
    status: Literal["passed", "failed"]
    results: list[dict[str, Any]]
    passed_count: int
    total_count: int
    cost_microunits: int
    duration_ms: int
    created_at: datetime


class AgentBaselineRequest(BaseModel):
    evaluation_run_id: str
    action: Literal["approve", "rollback"] = "approve"
    reason_code: str = Field(default="pilot_approved", min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class AgentBaselineDecisionResponse(BaseModel):
    id: str
    evaluation_run_id: str
    runtime: Literal["openclaw", "hermes"]
    action: Literal["approve", "rollback"]
    reason_code: str
    created_at: datetime


class AgentPilotGateResponse(BaseModel):
    scope: Literal["agent_pilot"] = "agent_pilot"
    runtime: Literal["openclaw", "hermes"]
    status: Literal["ready", "not_ready", "evaluation_required", "regression", "approval_required", "model_change"]
    pilot_ready: bool
    blockers: list[str]
    required_scenarios: list[str]
    latest_evaluation: AgentEvaluationRunResponse | None
    baseline: AgentBaselineDecisionResponse | None


class BlockingQuestionResponse(BaseModel):
    id: str
    priority: str
    target_entity: str
    target_id: str
    question: str


class ReadinessResponse(BaseModel):
    revision_id: str
    readiness_scope: Literal["automation_draft"] = "automation_draft"
    overall: int = Field(ge=0, le=100)
    draft_ready: bool
    automation_ready: bool
    blocking_question_count: int
    next_blocking_question: BlockingQuestionResponse | None
    categories: dict[str, ReadinessCategoryResponse]


class AnalystSessionCreateRequest(BaseModel):
    mode: Literal["discovery", "refinement", "export_preparation", "as_is_completion"] = "discovery"
    locale: str | None = Field(default=None, min_length=2, max_length=35)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        return normalize_locale(value) if value else None


class AnalystMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be blank.")
        return value


class InterviewImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_format: Literal["plain", "txt", "md", "srt", "vtt", "docx", "odt", "google_docs", "yandex_docs"] = "plain"
    language: str | None = Field(default=None, min_length=2, max_length=35)
    content: str = Field(min_length=1, max_length=500_000)
    source_url: str | None = Field(default=None, max_length=2_000)

    @field_validator("title", "content")
    @classmethod
    def trim_interview_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Interview content cannot be blank.")
        return value

    @field_validator("language")
    @classmethod
    def validate_interview_language(cls, value: str | None) -> str | None:
        return normalize_locale(value) if value else None


class InterviewSourceResolveRequest(BaseModel):
    source_type: Literal["google_docs", "yandex_docs", "docx", "odt"]
    url: str | None = Field(default=None, max_length=2_000)
    content_base64: str | None = Field(default=None, max_length=14_000_000)
    filename: str | None = Field(default=None, max_length=255)


class InterviewSourceResolveResponse(BaseModel):
    title: str
    source_format: Literal["google_docs", "yandex_docs", "docx", "odt"]
    content: str


class InterviewSegmentResponse(BaseModel):
    id: str | None = None
    ordinal: int
    speaker: str | None
    text: str
    start_ms: int | None
    end_ms: int | None


class InterviewSegmentUpdate(BaseModel):
    id: str | None = None
    speaker: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1, max_length=20_000)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @field_validator("speaker")
    @classmethod
    def trim_segment_speaker(cls, value: str | None) -> str | None:
        value = value.strip() if value else value
        return value or None

    @field_validator("text")
    @classmethod
    def trim_segment_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Interview segment text cannot be blank.")
        return value


class InterviewUpdateRequest(BaseModel):
    expected_segments_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=2, max_length=35)
    segments: list[InterviewSegmentUpdate] = Field(min_length=1, max_length=5_000)

    @field_validator("title")
    @classmethod
    def trim_interview_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("language")
    @classmethod
    def normalize_interview_language(cls, value: str) -> str:
        return normalize_locale(value)


class InterviewReviewRequest(BaseModel):
    expected_segments_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class InterviewEvidenceItem(BaseModel):
    statement: str = Field(min_length=1, max_length=4_000)
    segment_ids: list[str] = Field(min_length=1, max_length=50)


class InterviewCandidateItem(InterviewEvidenceItem):
    reason: str = Field(min_length=1, max_length=2_000)


class InterviewContradictionItem(BaseModel):
    summary: str = Field(min_length=1, max_length=4_000)
    segment_ids: list[str] = Field(min_length=2, max_length=50)
    question: str = Field(min_length=1, max_length=2_000)


class InterviewQuestionItem(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=2_000)
    priority: Literal["blocking", "important", "optional"]
    segment_ids: list[str] = Field(min_length=1, max_length=50)


class InterviewAnalysisResult(BaseModel):
    confirmed_facts: list[InterviewEvidenceItem] = Field(default_factory=list, max_length=100)
    candidate_facts: list[InterviewCandidateItem] = Field(default_factory=list, max_length=100)
    contradictions: list[InterviewContradictionItem] = Field(default_factory=list, max_length=100)
    clarification_questions: list[InterviewQuestionItem] = Field(default_factory=list, max_length=100)


class InterviewAnalysisResponse(BaseModel):
    id: str
    document_id: str
    segments_sha256: str
    result: InterviewAnalysisResult
    stale: bool
    provider: str
    model: str
    prompt_version: str
    created_at: datetime


class InterviewProposalRequest(BaseModel):
    base_revision_id: str
    selected_fact_indices: list[int] = Field(min_length=1, max_length=100)

    @field_validator("selected_fact_indices")
    @classmethod
    def unique_fact_indices(cls, value: list[int]) -> list[int]:
        if any(item < 0 for item in value) or len(value) != len(set(value)):
            raise ValueError("Selected fact indexes must be unique non-negative integers.")
        return value


class InterviewProcessDraftRequest(BaseModel):
    base_revision_id: str


class InterviewProposalEvidenceResponse(BaseModel):
    analysis_id: str
    segments_sha256: str
    selected_fact_indices: list[int]
    segment_ids: list[str]


class InterviewProposalResponse(BaseModel):
    message: "AnalystMessageResponse"
    proposal: "ProposedPatchResponse"
    evidence: InterviewProposalEvidenceResponse


class InterviewEvidenceSourceResponse(InterviewProposalEvidenceResponse):
    document_id: str
    document_title: str


class InterviewEvidenceFactResponse(BaseModel):
    statement: str
    occurrences: int
    sources: list[InterviewEvidenceSourceResponse]


class InterviewEvidenceSummaryResponse(BaseModel):
    session_id: str
    source_count: int
    confirmed_fact_count: int
    unique_fact_count: int
    duplicate_fact_count: int
    facts: list[InterviewEvidenceFactResponse]
    contradictions: list[InterviewContradictionItem]
    clarification_questions: list[InterviewQuestionItem]
    semantic_conflicts_pending: int = 0
    semantic_conflicts_confirmed: int = 0
    semantic_scan_required: bool = False
    can_build_draft: bool


class CrossInterviewFactReference(BaseModel):
    analysis_id: str
    fact_index: int = Field(ge=0)


class CrossInterviewConflictCandidate(BaseModel):
    summary: str = Field(min_length=1, max_length=4_000)
    question: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=2_000)
    fact_references: list[CrossInterviewFactReference] = Field(min_length=2, max_length=20)


class CrossInterviewConflictAnalysis(BaseModel):
    conflicts: list[CrossInterviewConflictCandidate] = Field(default_factory=list, max_length=100)


class CrossInterviewConflictResponse(CrossInterviewConflictCandidate):
    id: str
    session_id: str
    evidence_sha256: str
    status: Literal["pending", "confirmed", "dismissed"]
    segment_ids: list[str]
    resolved_by_user_id: str | None
    created_at: datetime
    resolved_at: datetime | None


class CrossInterviewConflictScanResponse(BaseModel):
    session_id: str
    evidence_sha256: str
    source_count: int
    fact_count: int
    conflicts: list[CrossInterviewConflictResponse]


class CrossInterviewConflictResolveRequest(BaseModel):
    action: Literal["confirm", "dismiss"]


class MultiInterviewProposalResponse(BaseModel):
    message: "AnalystMessageResponse"
    proposal: "ProposedPatchResponse"
    evidence_sources: list[InterviewEvidenceSourceResponse]


class InterviewTemplateMatchRequest(BaseModel):
    locale: str = Field(default="ru", min_length=2, max_length=35)
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        return normalize_locale(value)


class InterviewTemplateMatchResponse(BaseModel):
    analysis_id: str
    segments_sha256: str
    confirmed_fact_indices: list[int]
    suggestion: ProcessTemplateSuggestionResponse | None
    proposed_rubric_entry_ids: list[str]


class InterviewDocumentResponse(BaseModel):
    id: str | None = None
    session_id: str | None = None
    title: str
    source_format: str
    source_url: str | None = None
    language: str
    content_sha256: str
    segments_sha256: str
    status: Literal["draft", "reviewed", "purged"]
    data_residency: str = "local"
    retention_until: datetime | None = None
    purged_at: datetime | None = None
    purge_reason: Literal["manual", "retention"] | None = None
    segment_count: int
    segments: list[InterviewSegmentResponse]
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    latest_analysis: InterviewAnalysisResponse | None = None


class ProposedPatchCreateRequest(BaseModel):
    base_revision_id: str
    patch: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=4_000)
    source_message_id: str | None = None

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Proposal summary cannot be blank.")
        return value


class ProposedPatchResolveRequest(BaseModel):
    base_revision_id: str


class AnalystMessageResponse(BaseModel):
    id: str
    session_id: str
    revision_id: str
    role: str
    content: str
    locale: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    created_by_user_id: str | None
    created_at: datetime


class ProposedPatchResponse(BaseModel):
    id: str
    session_id: str
    project_id: str
    base_revision_id: str
    source_message_id: str | None
    patch: list[dict[str, Any]]
    summary: str
    validation: ValidationResult
    status: str
    accepted_revision_id: str | None
    created_by_user_id: str
    resolved_by_user_id: str | None
    created_at: datetime
    resolved_at: datetime | None
    draft_quality: "InterviewDraftQualityResponse | None" = None


class InterviewDraftQualityResponse(BaseModel):
    selected_fact_count: int
    total_confirmed_fact_count: int
    evidence_coverage: int = Field(ge=0, le=100)
    step_count: int
    edge_count: int
    decision_count: int
    open_question_count: int
    validation_warning_codes: list[str]
    readiness: int = Field(ge=0, le=100)
    draft_ready: bool


class AnalystSessionResponse(BaseModel):
    id: str
    project_id: str
    started_from_revision_id: str
    mode: str
    locale: str
    status: str
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class AnalystSessionDetailResponse(AnalystSessionResponse):
    messages: list[AnalystMessageResponse]
    proposed_patches: list[ProposedPatchResponse]
    interview_documents: list[InterviewDocumentResponse] = Field(default_factory=list)


class AnalystTurnResponse(BaseModel):
    user_message: AnalystMessageResponse
    assistant_message: AnalystMessageResponse
    proposed_patch: ProposedPatchResponse | None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    preferred_locale: str = Field(default="ru", min_length=2, max_length=35)

    @field_validator("preferred_locale")
    @classmethod
    def validate_preferred_locale(cls, value: str) -> str:
        return normalize_locale(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(RefreshRequest):
    pass


class WorkspaceMembershipResponse(BaseModel):
    workspace_id: str
    workspace_name: str
    role: str
    default_locale: str
    status: Literal["active", "archived"] = "active"
    archived_at: datetime | None = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    preferred_locale: str
    is_active: bool
    active_workspace_id: str | None
    workspaces: list[WorkspaceMembershipResponse]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
