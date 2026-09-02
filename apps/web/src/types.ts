export type Locale = 'ru' | 'en' | 'es'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface WorkspaceMembership {
  workspace_id: string
  workspace_name: string
  role: 'owner' | 'member'
  default_locale: string
  status: 'active' | 'archived'
  archived_at: string | null
}

export interface WorkspaceAuditEvent {
  id: string
  actorUserId: string
  action: string
  targetType: string
  targetId: string
  reason: string
  details: Record<string, unknown>
  createdAt: string
}

export interface WorkspaceMember {
  userId: string
  email: string
  role: 'owner' | 'member'
  joinedAt: string
}

export interface WorkspaceInvitation {
  id: string
  workspaceId: string
  email: string
  role: 'member'
  status: 'pending' | 'accepted' | 'revoked' | 'expired'
  expiresAt: string
  createdAt: string
}

export interface WorkspaceInvitationCreated extends WorkspaceInvitation {
  acceptanceToken: string
}

export interface User {
  id: string
  email: string
  preferred_locale: string
  is_active: boolean
  active_workspace_id: string | null
  workspaces: WorkspaceMembership[]
}

export type ServiceRole = 'user' | 'service_admin' | 'support' | 'billing_admin' | 'viewer'

export interface AdminIdentity {
  id: string
  email: string
  serviceRole: ServiceRole
  capabilities: {
    mode: 'hosted' | 'self_hosted'
    billingEnabled: boolean
    licenseMode: 'issuer' | 'consumer' | 'none'
    userManagement: boolean
    commercialStateManagement: boolean
  }
}

export interface AdminUser {
  id: string
  email: string
  serviceRole: ServiceRole
  isActive: boolean
  preferredLocale: string
  workspaceCount: number
  createdAt: string
}

export interface AdminWorkspace {
  id: string
  name: string
  defaultLocale: string
  status: 'active' | 'archived'
  archivedAt: string | null
  memberCount: number
  projectCount: number
  commercialState: null | {
    planId: string
    status: string
    source: string
    catalogVersion: string
    entitlementOverrides: Record<string, boolean | number>
    expiresAt: string | null
    graceUntil: string | null
  }
  license: null | { licenseId: string; status: string; expiresAt: string | null }
  createdAt: string
}

export interface AdminAuditEvent {
  id: string
  actorUserId: string
  workspaceId?: string | null
  action: string
  targetType: string
  targetId: string
  reason: string
  details: Record<string, unknown>
  createdAt: string
}

export interface AdminSelfHostedLicense {
  licenseId: string
  customerId: string
  deploymentId: string
  workspaceId: string
  planId: string
  issuedAt: string
  expiresAt: string
  graceUntil: string
  status: 'issued' | 'revoked'
  supersedesLicenseId: string | null
  revokedAt: string | null
  activationCode?: string
  envelope?: { payload: Record<string, unknown>; signature: string }
}

export interface AdminLLMUsage {
  summary: {
    periodStart: string
    periodEnd: string
    inputTokens: number
    outputTokens: number
    estimatedCostPicousd: number
    estimatedCostUsd: string
    unpricedRecords: number
    budgetPicousd: number
    budgetUsd: string
    warningPercent: number
    budgetRatio: number
    status: 'unconfigured' | 'ok' | 'warning' | 'exceeded'
  }
  breakdown: Array<{
    workspaceId: string
    provider: string
    model: string
    requestCount: number
    inputTokens: number
    outputTokens: number
    estimatedCostPicousd: number | null
  }>
  alerts: Array<{
    code: 'llm_budget_warning' | 'llm_budget_exceeded' | 'llm_usage_unpriced'
    severity: 'warning' | 'critical'
    estimatedCostUsd?: string
    budgetUsd?: string
    budgetRatio?: number
    recordCount?: number
  }>
}

export interface AdminUsage {
  items: Array<{
    workspaceId: string
    metric: 'llm_turn' | 'export' | 'runtime_publish' | 'agent_run'
    entitlementId: string
    periodStart: string
    periodEnd: string
    limit: number
    reserved: number
    consumed: number
    remaining: number | null
  }>
  alerts: Array<{
    code: 'usage_limit_warning' | 'usage_limit_exceeded'
    severity: 'warning' | 'critical'
    workspaceId: string
    metric: 'llm_turn' | 'export' | 'runtime_publish' | 'agent_run'
    limit: number
    used: number
    ratio: number
  }>
}

export interface AdminInvoices {
  items: Array<{
    id: string
    provider: string
    externalInvoiceId: string
    workspaceId: string | null
    subscriptionId: string | null
    providerStatus: 'draft' | 'open' | 'paid' | 'payment_failed' | 'void' | 'uncollectible'
    currency: string
    providerAmountDueMinor: number
    providerAmountPaidMinor: number
    periodStart: string
    periodEnd: string
    updatedAt: string
    reconciliation: null | {
      id: string
      status: 'matched' | 'mismatch' | 'unpriced' | 'unmapped' | 'stale'
      pricingCatalogVersion: string | null
      expectedAmountMinor: number | null
      discrepancyMinor: number | null
      usageSha256: string
      createdAt: string
    }
  }>
  alerts: Array<{
    code: 'billing_invoice_mismatch' | 'billing_invoice_unpriced' | 'billing_invoice_unmapped'
    severity: 'warning' | 'critical'
    invoiceId: string
    workspaceId: string | null
  }>
  total: number
  limit: number
  offset: number
}

export interface ActivityReportMetrics {
  workflowsCreated: number
  workflowsReady: number
  workflowsInProgress: number
  n8nPublications: number
  agentDeliveries: number
  agentRuns: number
  inputTokens: number
  outputTokens: number
  estimatedCostPicousd: number
  unpricedLlmRecords: number
  totalTokens: number
}

export interface AdminActivityReport {
  periodStart: string
  periodEnd: string
  generatedAt: string
  summary: ActivityReportMetrics
  workspaces: Array<ActivityReportMetrics & { workspaceId: string; workspaceName: string }>
}

export interface AdminPage<T> { items: T[]; total: number; limit: number; offset: number }

export type LLMProvider = 'deepseek' | 'openai' | 'openai_compatible'

export interface LLMCredentialSummary {
  provider: LLMProvider
  base_url: string
  model: string
  key_configured: boolean
  is_active: boolean
  selected: boolean
  updated_at: string
}

export interface LLMConfiguration {
  deployment_profile: {
    id: string
    revision: number
    product_name: string
    allowed_providers: LLMProvider[]
    system_fallback_allowed: boolean
    system_fallback_enabled: boolean
    custom_base_url_allowed: boolean
    local_endpoints_allowed: boolean
    credential_management_enabled: boolean
  }
  providers: Array<{ id: LLMProvider; default_base_url: string; requires_api_key: boolean }>
  credentials: LLMCredentialSummary[]
  selected_provider: LLMProvider | null
  encryption_configured: boolean
}

export interface LLMCredentialInput {
  provider: LLMProvider
  api_key: string | null
  base_url: string
  model: string
}

export interface RuntimeConnectionProfile {
  id: string
  workspace_id: string
  name: string
  kind: 'n8n' | 'openclaw' | 'hermes'
  endpoint_url: string
  secret_ref: string
  n8n_minor: '2.32' | '2.31' | '2.30' | null
  status: 'draft' | 'verified' | 'failed' | 'disabled'
  detected_version: string | null
  last_check_code: string | null
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export type RuntimeConnectionInput = Pick<RuntimeConnectionProfile, 'name' | 'kind' | 'endpoint_url' | 'secret_ref' | 'n8n_minor'>

export interface RuntimeConnectionCheck {
  profile: RuntimeConnectionProfile
  result_code: string
  detected_version: string | null
}

export interface N8nPublicationPreview {
  profile_id: string
  revision_id: string
  target_minor: '2.32' | '2.31' | '2.30'
  workflow_name: string
  workflow_sha256: string
  node_count: number
  connection_count: number
  active: false
  source_mode: 'generated' | 'round_trip'
}

export interface N8nPublication {
  id: string
  project_id: string
  revision_id: string
  profile_id: string
  workflow_sha256: string
  remote_workflow_id: string | null
  status: 'publishing' | 'published' | 'failed' | 'deleted' | 'deletion_failed'
  last_error_code: string | null
  created_at: string
  published_at: string | null
  deleted_at: string | null
}

export interface AgentPackageDeliveryPreview {
  profile_id: string
  revision_id: string
  runtime: 'openclaw' | 'hermes'
  process_name: string
  package_sha256: string
  package_size: number
  file_count: number
  readiness_score: number
  blocker_count: number
  ready: boolean
  active: false
}

export interface AgentPackageDelivery {
  id: string
  project_id: string
  revision_id: string
  profile_id: string
  runtime: 'openclaw' | 'hermes'
  package_sha256: string
  package_size: number
  file_count: number
  remote_package_id: string | null
  status: 'storing' | 'stored' | 'failed' | 'deleted' | 'deletion_failed'
  last_error_code: string | null
  created_at: string
  stored_at: string | null
  deleted_at: string | null
}

export interface ProcessStep {
  id: string
  type: 'start' | 'end' | 'human_task' | 'system_task' | 'decision' | 'timer' | 'external_event'
  title: string
  description: string
  actorId: string | null
  systemId: string | null
  inputs: string[]
  outputs: string[]
  operation: { kind: string; name: string; parameters: Record<string, unknown> }
  missingFields: string[]
  automationHint: { target: string; nodeType: string } | null
  execution: {
    performedBy: 'human' | 'system' | 'ai'
    autonomy: 'manual' | 'assist' | 'supervised' | 'autonomous'
    approvalRequired: boolean
    restrictions: string[]
  }
  agentConfig?: {
    knowledgeSources: string[]
    allowedStateIds: string[]
    stopConditions: string[]
    auditEvents: string[]
    escalation: { missingSource: string; conflictingSources: string; lowConfidence: string; riskyAction: string }
  } | null
  customLogic?: {
    strategy: 'python_code' | 'python_service' | 'typescript_node'
    reasonStandardNodesInsufficient: string
    businessRuleIds: string[]
    runtimeProfile: 'n8n_native_python' | 'external_python_service' | 'native_typescript_node'
    dependencyProfile?: 'core' | 'dates' | 'validation'
    fallbackReason?: 'python_runtime_unavailable' | 'service_network_forbidden' | 'native_installation_required'
    operationSpec?: { kind: 'numeric_threshold'; inputField: string; outputField: string; operator: '<' | '<=' | '==' | '!=' | '>=' | '>'; threshold: number }
    source: string
    inputExample: unknown
    outputExample: unknown
    errorExample: unknown
    expectedError: 'TypeError' | 'ValueError' | 'KeyError'
    errorCases: string[]
    prohibitions: string[]
    generatorVersion: string
    contentHash: string
    executionEvidence?: { status: 'passed'; contentHash: string; runner: string; dependencyProfile?: 'core' | 'dates' | 'validation'; operationSpecHash?: string; checks: string[]; durationMs: number }
    approvalStatus: 'draft' | 'approved' | 'rejected'
  } | null
}

export interface ProcessEdge {
  id: string
  from: string
  to: string
  condition: { left: string; operator: string; right: unknown } | null
  ruleIds: string[]
}

export interface ProcessIR {
  schemaVersion: string
  process: { id: string; name: string; description: string; domain: string; maturity: string }
  classification?: {
    rubricVersion: string
    status: 'proposed' | 'confirmed'
    entryIds: string[]
    classifiedAt: string | null
    classifiedByUserId: string | null
  }
  passport: {
    goal: string
    ownerActorId: string | null
    startsWhen: string
    endsWhen: string
    inScope: string[]
    outOfScope: string[]
    successMetrics: Array<{ id: string; name: string; target: string; unit: string }>
  }
  actors: Array<{ id: string; name: string; type: string; responsibilities: string[] }>
  systems: Array<{ id: string; name: string; type: string; integrationStatus: string; notes: string }>
  dataObjects: Array<{ id: string; name: string; fields: unknown[] }>
  states: Array<{ id: string; dataObjectId: string; name: string; description: string; initial: boolean; terminal: boolean }>
  stateTransitions: Array<{ id: string; dataObjectId: string; fromStateId: string | null; toStateId: string; trigger: string; ruleIds: string[] }>
  businessRules: Array<{ id: string; name: string; description: string; type: string; source: string; appliesToStepIds: string[] }>
  steps: ProcessStep[]
  edges: ProcessEdge[]
  exceptions: Array<Record<string, unknown>>
  openQuestions: Array<{
    id: string
    priority: string
    target: { entity: string; id: string }
    question: string
    blocksAutomationReady: boolean
  }>
  readiness: Record<string, unknown>
}

export interface ProcessTemplate {
  id: string
  category: string
  category_name: string
  name: string
  description: string
  step_count: number
  actor_count: number
  system_count: number
  preview_steps: string[]
  process_ir: ProcessIR | null
  status: 'ready' | 'interview_draft'
  priority: string | null
  ai_required: boolean | null
  human_in_loop: boolean | null
  automation_pattern: string | null
  source_template_id: number | null
  source_url: string | null
  library_number: number | null
  agent_enabled: boolean
  agent_topology: string | null
  search_terms: string[]
  rubric_entry_ids: string[]
  source: 'catalog' | 'user'
  collection_ids: string[]
  favorite: boolean
}

export interface TemplateCollection {
  id: string
  name: string
  is_favorites: boolean
  item_count: number
  created_at: string
}

export interface TemplateCollectionItem {
  collection_id: string
  template_source: 'catalog' | 'user'
  template_id: string
}

export interface N8nImportDiagnostics {
  status: string
  nodeCount: number
  connectionCount: number
  knownNodeCount: number
  unknownNodes: Array<{ name: string; type: string }>
  danglingConnections: Array<{ from: string; to: string }>
  credentialReferences: Array<{ node: string; types: string[]; names: string[] }>
  warnings: string[]
}

export interface N8nImportResult {
  project: Project
  artifact_id: string
  source_minor: string
  source_sha256: string
  diagnostics: N8nImportDiagnostics
}

export interface PythonCodeValidation {
  valid: boolean
  artifact: NonNullable<ProcessStep['customLogic']>
  checks: Record<'syntax' | 'policy' | 'provenance' | 'fixtures' | 'execution', 'passed' | 'failed'>
  errors: Array<{ code: string; message: string }>
  execution: { status: 'passed'; contentHash: string; runner: string; checks: string[]; durationMs: number } | null
}

export interface PythonCodeGeneration {
  artifact: NonNullable<ProcessStep['customLogic']>
  template: string
}

export interface RubricEntry {
  id: string
  code: string
  parent_id: string | null
  name: string
  description: string
  synonyms: string[]
  deprecated: boolean
}

export interface RubricDimension {
  id: string
  name: string
  entries: RubricEntry[]
}

export interface Rubric {
  version: string
  status: string
  dimensions: RubricDimension[]
}

export interface ProcessTemplateSuggestion {
  template: ProcessTemplate
  confidence: number
  reason: string
  matched_signals: string[]
}

export interface ValidationResult {
  valid: boolean
  counts: { errors: number; warnings: number }
  issues: Array<{ severity: string; code: string; message: string; path: string }>
}

export interface Revision {
  id: string
  project_id: string
  version_number: number
  schema_version: string
  process_ir: ProcessIR
  forward_patch: Array<Record<string, unknown>> | null
  inverse_patch: Array<Record<string, unknown>> | null
  validation: ValidationResult
  parent_revision_id: string | null
  restored_from_revision_id: string | null
  source: string
  perspective: 'as_is' | 'to_be'
  created_by_user_id: string
  created_at: string
}

export interface Project {
  id: string
  workspace_id: string
  name: string
  description: string
  default_locale: string
  status: string
  target_mode: 'process' | 'agent'
  current_revision_id: string
  current_revision: Revision
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface ProjectArchiveValidation {
  valid: boolean
  archive_sha256: string
  source_project_id: string
  project_name: string
  format_version: string
  counts: Record<string, number>
  warnings: string[]
  already_restored_project_id: string | null
}

export interface ProjectArchiveRestore {
  project: Project
  archive_sha256: string
  already_restored: boolean
}

export interface AgentReadiness {
  scope: 'agent_deployment'
  overall: number
  agentReady: boolean
  blockers: string[]
  blockingQuestionCount: number
  categories: Record<string, ReadinessCategory>
}

export interface AgentRunEvent {
  id: string
  sequence: number
  event_type: string
  actor_type: 'user' | 'system' | 'agent'
  reason_code: string | null
  metrics: Record<string, number | boolean>
  created_at: string
}

export interface AgentRun {
  id: string
  project_id: string
  revision_id: string
  runtime: 'openclaw' | 'hermes'
  status: 'created' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'escalated' | 'cancelled'
  contract_version: string
  idempotency_key: string
  limits: { max_steps: number; max_tool_calls: number; timeout_seconds: number; max_cost_microunits: number }
  usage: { steps: number; tool_calls: number; cost_microunits: number }
  started_at: string | null
  ended_at: string | null
  created_at: string
  updated_at: string
  events: AgentRunEvent[]
  dispatch_status: 'queued' | 'leased' | 'retry_wait' | 'dispatched' | 'dead_letter' | 'cancelled' | null
  dispatch_attempts: number
  incident_id: string | null
  incident_status: 'open' | 'resolved' | 'replayed' | null
  incident_category: 'dispatch' | 'runtime' | 'limit' | 'timeout' | 'escalation' | null
  incident_reason_code: string | null
  replay_run_id: string | null
}

export interface AgentDispatch {
  run: AgentRun
  job: {
    id: string
    run_id: string
    status: NonNullable<AgentRun['dispatch_status']>
    attempt_count: number
    max_attempts: number
    last_error_code: string | null
  }
}

export interface AgentIncidentReplay {
  incident: { id: string; status: 'replayed'; replay_run_id: string }
  dispatch: AgentDispatch
}

export interface AgentEvaluationRun {
  id: string
  project_id: string
  revision_id: string
  runtime: 'openclaw' | 'hermes'
  suite_version: string
  status: 'passed' | 'failed'
  results: Array<{ scenario_id: string; passed: boolean; reason_code: string | null }>
  passed_count: number
  total_count: number
  cost_microunits: number
  duration_ms: number
  created_at: string
}

export interface AgentPilotGate {
  scope: 'agent_pilot'
  runtime: 'openclaw' | 'hermes'
  status: 'ready' | 'not_ready' | 'evaluation_required' | 'regression' | 'approval_required' | 'model_change'
  pilot_ready: boolean
  blockers: string[]
  required_scenarios: string[]
  latest_evaluation: AgentEvaluationRun | null
  baseline: null | { id: string; evaluation_run_id: string; runtime: 'openclaw' | 'hermes'; action: 'approve' | 'rollback'; reason_code: string; created_at: string }
}

export interface ReadinessCategory {
  score: number
  status: 'ok' | 'warning' | 'blocked'
  reason_codes: string[]
}

export interface Readiness {
  revision_id: string
  readiness_scope: 'automation_draft'
  overall: number
  draft_ready: boolean
  automation_ready: boolean
  blocking_question_count: number
  next_blocking_question: null | {
    id: string
    priority: string
    target_entity: string
    target_id: string
    question: string
  }
  categories: Record<string, ReadinessCategory>
}

export interface AnalystMessage {
  id: string
  session_id: string
  revision_id: string
  role: 'user' | 'assistant'
  content: string
  locale: string
  provider: string | null
  model: string | null
  prompt_version: string | null
  created_at: string
}

export interface ProposedPatch {
  id: string
  session_id: string
  project_id: string
  base_revision_id: string
  source_message_id: string | null
  patch: Array<Record<string, unknown>>
  summary: string
  validation: ValidationResult
  status: 'pending' | 'accepted' | 'rejected'
  accepted_revision_id: string | null
  created_at: string
  draft_quality?: null | {
    selected_fact_count: number
    total_confirmed_fact_count: number
    evidence_coverage: number
    step_count: number
    edge_count: number
    decision_count: number
    open_question_count: number
    validation_warning_codes: string[]
    readiness: number
    draft_ready: boolean
  }
}

export interface AnalystSession {
  id: string
  project_id: string
  started_from_revision_id: string
  mode: 'discovery' | 'refinement' | 'export_preparation' | 'as_is_completion'
  locale: string
  status: string
  created_at: string
  updated_at: string
}

export interface AnalystSessionDetail extends AnalystSession {
  messages: AnalystMessage[]
  proposed_patches: ProposedPatch[]
  interview_documents: InterviewDocument[]
}

export interface InterviewSegment {
  id: string | null
  ordinal: number
  speaker: string | null
  text: string
  start_ms: number | null
  end_ms: number | null
}

export interface InterviewDocument {
  id: string | null
  session_id: string | null
  title: string
  source_format: 'plain' | 'txt' | 'md' | 'srt' | 'vtt' | 'docx' | 'odt' | 'google_docs' | 'yandex_docs'
  source_url: string | null
  language: string
  content_sha256: string
  segments_sha256: string
  status: 'draft' | 'reviewed' | 'purged'
  data_residency: string
  retention_until: string | null
  purged_at: string | null
  purge_reason: 'manual' | 'retention' | null
  segment_count: number
  segments: InterviewSegment[]
  created_at: string | null
  reviewed_at: string | null
  latest_analysis: InterviewAnalysis | null
}

export interface InterviewEvidenceItem { statement: string; segment_ids: string[] }
export interface InterviewCandidateItem extends InterviewEvidenceItem { reason: string }
export interface InterviewContradictionItem { summary: string; segment_ids: string[]; question: string }
export interface InterviewQuestionItem { question: string; reason: string; priority: 'blocking' | 'important' | 'optional'; segment_ids: string[] }
export interface InterviewAnalysis {
  id: string
  document_id: string
  segments_sha256: string
  result: { confirmed_facts: InterviewEvidenceItem[]; candidate_facts: InterviewCandidateItem[]; contradictions: InterviewContradictionItem[]; clarification_questions: InterviewQuestionItem[] }
  stale: boolean
  provider: string
  model: string
  prompt_version: string
  created_at: string
}

export interface InterviewProposalResponse {
  message: AnalystMessage
  proposal: ProposedPatch
  evidence: {
    analysis_id: string
    segments_sha256: string
    selected_fact_indices: number[]
    segment_ids: string[]
  }
}

export interface InterviewEvidenceSource {
  analysis_id: string
  document_id: string
  document_title: string
  segments_sha256: string
  selected_fact_indices: number[]
  segment_ids: string[]
}

export interface InterviewEvidenceSummary {
  session_id: string
  source_count: number
  confirmed_fact_count: number
  unique_fact_count: number
  duplicate_fact_count: number
  facts: Array<{ statement: string; occurrences: number; sources: InterviewEvidenceSource[] }>
  contradictions: InterviewContradictionItem[]
  clarification_questions: InterviewQuestionItem[]
  semantic_conflicts_pending: number
  semantic_conflicts_confirmed: number
  semantic_scan_required: boolean
  can_build_draft: boolean
}

export interface CrossInterviewConflict {
  id: string
  session_id: string
  evidence_sha256: string
  summary: string
  question: string
  reason: string
  fact_references: Array<{ analysis_id: string; fact_index: number }>
  segment_ids: string[]
  status: 'pending' | 'confirmed' | 'dismissed'
  resolved_by_user_id: string | null
  created_at: string
  resolved_at: string | null
}

export interface CrossInterviewConflictScan {
  session_id: string
  evidence_sha256: string
  source_count: number
  fact_count: number
  conflicts: CrossInterviewConflict[]
}

export interface MultiInterviewProposalResponse {
  message: AnalystMessage
  proposal: ProposedPatch
  evidence_sources: InterviewEvidenceSource[]
}

export interface InterviewTemplateMatch {
  analysis_id: string
  segments_sha256: string
  confirmed_fact_indices: number[]
  suggestion: ProcessTemplateSuggestion | null
  proposed_rubric_entry_ids: string[]
}

export interface AnalystTurn {
  user_message: AnalystMessage
  assistant_message: AnalystMessage
  proposed_patch: ProposedPatch | null
}
