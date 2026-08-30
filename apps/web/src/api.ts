import type {
  AnalystSession,
  AnalystSessionDetail,
  AnalystTurn,
  InterviewAnalysis,
  InterviewDocument,
  AgentReadiness,
  AgentPackageDelivery,
  AgentPackageDeliveryPreview,
  AgentDispatch,
  AgentIncidentReplay,
  AgentEvaluationRun,
  AgentPilotGate,
  AgentRun,
  Locale,
  LLMConfiguration,
  LLMCredentialInput,
  N8nImportResult,
  N8nPublication,
  N8nPublicationPreview,
  Project,
  ProcessTemplate,
  ProcessTemplateSuggestion,
  ProcessIR,
  ProcessStep,
  PythonCodeGeneration, PythonCodeValidation,
  ProjectArchiveRestore,
  ProjectArchiveValidation,
  ProposedPatch, InterviewProposalResponse, InterviewTemplateMatch,
  Readiness,
  RuntimeConnectionCheck,
  RuntimeConnectionInput,
  RuntimeConnectionProfile,
  Revision,
  Rubric,
  TemplateCollection,
  TemplateCollectionItem,
  TokenPair,
  User,
  WorkspaceMembership,
  WorkspaceMember,
  WorkspaceInvitation,
  WorkspaceInvitationCreated,
  WorkspaceAuditEvent,
  AdminIdentity,
  AdminUser,
  AdminWorkspace,
  AdminAuditEvent,
  AdminLLMUsage,
  AdminUsage,
  AdminInvoices,
  AdminActivityReport,
  AdminPage,
} from './types'

const ACCESS_TOKEN = 'apa_access_token'
const REFRESH_TOKEN = 'apa_refresh_token'

function newIdempotencyKey(prefix = 'request') {
  const uuid = globalThis.crypto?.randomUUID?.()
  return uuid ? `${prefix}:${uuid}` : `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message)
  }
}

function saveTokens(tokens: TokenPair) {
  localStorage.setItem(ACCESS_TOKEN, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN, tokens.refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN)
  localStorage.removeItem(REFRESH_TOKEN)
}

export function hasSession() {
  return Boolean(localStorage.getItem(REFRESH_TOKEN))
}

async function parseError(response: Response) {
  const payload = await response.json().catch(() => null)
  const detail = payload?.detail
  return new ApiError(
    typeof detail === 'string' ? detail : detail?.message || `Request failed (${response.status})`,
    response.status,
    detail?.code,
  )
}

async function rotateTokens() {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN)
  if (!refreshToken) throw new ApiError('Session expired', 401, 'session_expired')
  const response = await fetch('/api/v1/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) {
    clearTokens()
    throw await parseError(response)
  }
  const tokens = (await response.json()) as TokenPair
  saveTokens(tokens)
  return tokens.access_token
}

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const token = localStorage.getItem(ACCESS_TOKEN)
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { ...init, headers })
  if (response.status === 401 && !retried && localStorage.getItem(REFRESH_TOKEN)) {
    await rotateTokens()
    return request<T>(path, init, true)
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function authenticate(mode: 'login' | 'register', email: string, password: string, locale: Locale) {
  const payload = mode === 'register' ? { email, password, preferred_locale: locale } : { email, password }
  const tokens = await request<TokenPair>(`/api/v1/auth/${mode}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  saveTokens(tokens)
  return tokens
}

export const api = {
  me: () => request<User>('/api/v1/auth/me'),
  adminMe: () => request<AdminIdentity>('/api/v1/admin/me'),
  adminUsers: () => request<AdminPage<AdminUser>>('/api/v1/admin/users?limit=100'),
  adminWorkspaces: () => request<AdminPage<AdminWorkspace>>('/api/v1/admin/workspaces?limit=100'),
  adminAuditEvents: () => request<AdminPage<AdminAuditEvent>>('/api/v1/admin/audit-events?limit=100'),
  adminLlmUsage: () => request<AdminLLMUsage>('/api/v1/admin/billing/llm-usage'),
  adminUsage: () => request<AdminUsage>('/api/v1/admin/billing/usage'),
  adminInvoices: () => request<AdminInvoices>('/api/v1/admin/billing/invoices?limit=100'),
  adminActivityReport: () => request<AdminActivityReport>('/api/v1/admin/reports/activity'),
  workspaceActivityReport: (workspaceId: string) => request<AdminActivityReport>(`/api/v1/workspaces/${workspaceId}/activity-report`),
  renameWorkspace: (workspaceId: string, name: string) => request<{ id: string; name: string; defaultLocale: string }>(`/api/v1/workspaces/${workspaceId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  createWorkspace: (name: string, defaultLocale: Locale) => request<WorkspaceMembership>('/api/v1/workspaces', { method: 'POST', body: JSON.stringify({ name, default_locale: defaultLocale }) }),
  activateWorkspace: (workspaceId: string) => request<WorkspaceMembership>(`/api/v1/workspaces/${workspaceId}/active`, { method: 'PUT' }),
  workspaceMembers: (workspaceId: string) => request<WorkspaceMember[]>(`/api/v1/workspaces/${workspaceId}/members`),
  workspaceInvitations: (workspaceId: string) => request<WorkspaceInvitation[]>(`/api/v1/workspaces/${workspaceId}/invitations`),
  createWorkspaceInvitation: (workspaceId: string, email: string) => request<WorkspaceInvitationCreated>(`/api/v1/workspaces/${workspaceId}/invitations`, { method: 'POST', body: JSON.stringify({ email }) }),
  revokeWorkspaceInvitation: (workspaceId: string, invitationId: string) => request<WorkspaceInvitation>(`/api/v1/workspaces/${workspaceId}/invitations/${invitationId}`, { method: 'DELETE' }),
  acceptWorkspaceInvitation: (token: string) => request<WorkspaceMembership>('/api/v1/workspaces/invitations/accept', { method: 'POST', body: JSON.stringify({ token }) }),
  updateWorkspaceMemberRole: (workspaceId: string, userId: string, role: 'owner' | 'member') => request<WorkspaceMember>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  transferWorkspaceOwnership: (workspaceId: string, targetUserId: string) => request<WorkspaceMember[]>(`/api/v1/workspaces/${workspaceId}/ownership-transfer`, { method: 'POST', body: JSON.stringify({ target_user_id: targetUserId }) }),
  removeWorkspaceMember: (workspaceId: string, userId: string) => request<{ removed: boolean; userId: string }>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, { method: 'DELETE' }),
  archiveWorkspace: (workspaceId: string) => request<WorkspaceMembership>(`/api/v1/workspaces/${workspaceId}/archive`, { method: 'POST' }),
  restoreWorkspace: (workspaceId: string) => request<WorkspaceMembership>(`/api/v1/workspaces/${workspaceId}/restore`, { method: 'POST' }),
  workspaceAuditEvents: (workspaceId: string) => request<WorkspaceAuditEvent[]>(`/api/v1/workspaces/${workspaceId}/audit-events?limit=20`),
  llmConfiguration: () => request<LLMConfiguration>('/api/v1/llm/configuration'),
  saveLlmCredential: (input: LLMCredentialInput) => request(`/api/v1/llm/credentials/${input.provider}`, { method: 'PUT', body: JSON.stringify(input) }),
  selectLlmProvider: (provider: LLMCredentialInput['provider']) => request<void>('/api/v1/llm/preference', { method: 'PUT', body: JSON.stringify({ provider }) }),
  deleteLlmCredential: (provider: LLMCredentialInput['provider']) => request<void>(`/api/v1/llm/credentials/${provider}`, { method: 'DELETE' }),
  runtimeConnections: (workspaceId: string) => request<RuntimeConnectionProfile[]>(`/api/v1/workspaces/${workspaceId}/runtime-connections`),
  createRuntimeConnection: (workspaceId: string, input: RuntimeConnectionInput) => request<RuntimeConnectionProfile>(`/api/v1/workspaces/${workspaceId}/runtime-connections`, { method: 'POST', body: JSON.stringify(input) }),
  updateRuntimeConnection: (profileId: string, input: RuntimeConnectionInput) => request<RuntimeConnectionProfile>(`/api/v1/runtime-connections/${profileId}`, { method: 'PUT', body: JSON.stringify(input) }),
  verifyRuntimeConnection: (profileId: string) => request<RuntimeConnectionCheck>(`/api/v1/runtime-connections/${profileId}/verify`, { method: 'POST' }),
  disableRuntimeConnection: (profileId: string) => request<RuntimeConnectionProfile>(`/api/v1/runtime-connections/${profileId}/disable`, { method: 'POST' }),
  deleteRuntimeConnection: (profileId: string) => request<void>(`/api/v1/runtime-connections/${profileId}`, { method: 'DELETE' }),
  previewN8nPublication: (projectId: string, profileId: string, revisionId: string) => request<N8nPublicationPreview>(`/api/v1/projects/${projectId}/n8n-publications/preview`, { method: 'POST', body: JSON.stringify({ profile_id: profileId, revision_id: revisionId }) }),
  n8nPublications: (projectId: string) => request<N8nPublication[]>(`/api/v1/projects/${projectId}/n8n-publications`),
  publishN8n: (projectId: string, profileId: string, revisionId: string, workflowSha256: string) => request<N8nPublication>(`/api/v1/projects/${projectId}/n8n-publications`, { method: 'POST', body: JSON.stringify({ profile_id: profileId, revision_id: revisionId, expected_workflow_sha256: workflowSha256, idempotency_key: newIdempotencyKey('n8n') }) }),
  deleteN8nPublication: (publicationId: string) => request<N8nPublication>(`/api/v1/n8n-publications/${publicationId}`, { method: 'DELETE' }),
  previewAgentPackageDelivery: (projectId: string, profileId: string, revisionId: string) => request<AgentPackageDeliveryPreview>(`/api/v1/projects/${projectId}/agent-package-deliveries/preview`, { method: 'POST', body: JSON.stringify({ profile_id: profileId, revision_id: revisionId }) }),
  agentPackageDeliveries: (projectId: string) => request<AgentPackageDelivery[]>(`/api/v1/projects/${projectId}/agent-package-deliveries`),
  deliverAgentPackage: (projectId: string, profileId: string, revisionId: string, packageSha256: string) => request<AgentPackageDelivery>(`/api/v1/projects/${projectId}/agent-package-deliveries`, { method: 'POST', body: JSON.stringify({ profile_id: profileId, revision_id: revisionId, expected_package_sha256: packageSha256, idempotency_key: newIdempotencyKey('agent-package') }) }),
  deleteAgentPackageDelivery: (deliveryId: string) => request<AgentPackageDelivery>(`/api/v1/agent-package-deliveries/${deliveryId}`, { method: 'DELETE' }),
  projects: (workspaceId?: string) => request<Project[]>(`/api/v1/projects${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''}`),
  templates: (locale: Locale, rubricEntryIds: string[] = []) => {
    const params = new URLSearchParams({ locale })
    rubricEntryIds.forEach((id) => params.append('rubricEntryId', id))
    return request<ProcessTemplate[]>(`/api/v1/process-templates?${params.toString()}`)
  },
  rubric: (locale: Locale) => request<Rubric>(`/api/v1/rubric?locale=${encodeURIComponent(locale)}`),
  userTemplates: (locale: Locale) => request<ProcessTemplate[]>(`/api/v1/user-templates?locale=${encodeURIComponent(locale)}`),
  templateCollections: () => request<TemplateCollection[]>('/api/v1/template-collections'),
  templateCollectionItems: () => request<TemplateCollectionItem[]>('/api/v1/template-collection-items'),
  createTemplateCollection: (name: string) => request<TemplateCollection>('/api/v1/template-collections', { method: 'POST', body: JSON.stringify({ name }) }),
  addTemplateToCollection: (collectionId: string, templateSource: 'catalog' | 'user', templateId: string) => request<void>(`/api/v1/template-collections/${collectionId}/items`, { method: 'POST', body: JSON.stringify({ template_source: templateSource, template_id: templateId }) }),
  removeTemplateFromCollection: (collectionId: string, templateSource: 'catalog' | 'user', templateId: string) => request<void>(`/api/v1/template-collections/${collectionId}/items/${templateSource}/${encodeURIComponent(templateId)}`, { method: 'DELETE' }),
  saveProjectAsTemplate: (projectId: string, name: string, description: string, collectionIds: string[], favorite: boolean) => request<ProcessTemplate>(`/api/v1/projects/${projectId}/user-templates`, { method: 'POST', body: JSON.stringify({ name, description, collection_ids: collectionIds, favorite }) }),
  template: (id: string, locale: Locale) => request<ProcessTemplate>(`/api/v1/process-templates/${encodeURIComponent(id)}?locale=${encodeURIComponent(locale)}`),
  suggestTemplate: (text: string, locale: Locale, excludedIds: string[] = [], rubricEntryIds: string[] = []) =>
    request<ProcessTemplateSuggestion | null>('/api/v1/process-templates/suggest', {
      method: 'POST',
      body: JSON.stringify({ text, locale, excluded_ids: excludedIds, rubric_entry_ids: rubricEntryIds }),
    }),
  project: (id: string) => request<Project>(`/api/v1/projects/${id}`),
  readiness: (id: string) => request<Readiness>(`/api/v1/projects/${id}/readiness`),
  agentReadiness: (id: string) => request<AgentReadiness>(`/api/v1/projects/${id}/agent-readiness`),
  agentRuns: (id: string) => request<AgentRun[]>(`/api/v1/projects/${id}/agent-runs`),
  dispatchAgent: (id: string, runtime: 'openclaw' | 'hermes') => request<AgentDispatch>(`/api/v1/projects/${id}/agent-dispatches`, {
    method: 'POST',
    body: JSON.stringify({ runtime, idempotency_key: newIdempotencyKey('agent-run') }),
  }),
  resolveAgentIncident: (incidentId: string) => request(`/api/v1/agent-incidents/${incidentId}/resolve`, { method: 'POST', body: JSON.stringify({ resolution_code: 'reviewed_no_retry' }) }),
  replayAgentIncident: (incidentId: string, revision: 'original' | 'current') => request<AgentIncidentReplay>(`/api/v1/agent-incidents/${incidentId}/replay`, {
    method: 'POST',
    body: JSON.stringify({ revision, resolution_code: revision === 'current' ? 'process_revised' : 'configuration_fixed', idempotency_key: newIdempotencyKey('agent-replay') }),
  }),
  agentPilotGate: (id: string, runtime: 'openclaw' | 'hermes') => request<AgentPilotGate>(`/api/v1/projects/${id}/agent-pilot-gate?runtime=${runtime}`),
  agentEvaluations: (id: string) => request<AgentEvaluationRun[]>(`/api/v1/projects/${id}/agent-evaluations`),
  approveAgentBaseline: (id: string, evaluationRunId: string) => request(`/api/v1/projects/${id}/agent-baselines`, { method: 'POST', body: JSON.stringify({ evaluation_run_id: evaluationRunId, action: 'approve', reason_code: 'pilot_approved' }) }),
  setTargetMode: (id: string, targetMode: 'process' | 'agent') =>
    request<Project>(`/api/v1/projects/${id}/target-mode`, {
      method: 'PATCH',
      body: JSON.stringify({ target_mode: targetMode }),
    }),
  revisions: (id: string) => request<Revision[]>(`/api/v1/projects/${id}/revisions`),
  sessions: (id: string) => request<AnalystSession[]>(`/api/v1/projects/${id}/analyst/sessions`),
  session: (id: string) => request<AnalystSessionDetail>(`/api/v1/analyst/sessions/${id}`),
  createSession: (projectId: string, locale: Locale, mode: 'discovery' | 'as_is_completion' = 'discovery') =>
    request<AnalystSession>(`/api/v1/projects/${projectId}/analyst/sessions`, {
      method: 'POST',
      body: JSON.stringify({ mode, locale }),
    }),
  sendTurn: (sessionId: string, content: string) =>
    request<AnalystTurn>(`/api/v1/analyst/sessions/${sessionId}/turns`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  previewInterview: (sessionId: string, title: string, sourceFormat: InterviewDocument['source_format'], content: string, language: Locale, sourceUrl: string | null = null) =>
    request<InterviewDocument>(`/api/v1/analyst/sessions/${sessionId}/interviews/preview`, { method: 'POST', body: JSON.stringify({ title, source_format: sourceFormat, source_url: sourceUrl, content, language }) }),
  importInterview: (sessionId: string, title: string, sourceFormat: InterviewDocument['source_format'], content: string, language: Locale, sourceUrl: string | null = null) =>
    request<InterviewDocument>(`/api/v1/analyst/sessions/${sessionId}/interviews`, { method: 'POST', body: JSON.stringify({ title, source_format: sourceFormat, source_url: sourceUrl, content, language }) }),
  resolveInterviewSource: (sessionId: string, sourceType: 'google_docs' | 'yandex_docs' | 'docx' | 'odt', values: { url?: string; content_base64?: string; filename?: string }) =>
    request<{ title: string; source_format: InterviewDocument['source_format']; content: string }>(`/api/v1/analyst/sessions/${sessionId}/interviews/resolve-source`, { method: 'POST', body: JSON.stringify({ source_type: sourceType, ...values }) }),
  updateInterview: (document: InterviewDocument) => request<InterviewDocument>(`/api/v1/analyst/interviews/${document.id}`, { method: 'PUT', body: JSON.stringify({ expected_segments_sha256: document.segments_sha256, title: document.title, language: document.language, segments: document.segments.map(({ id, speaker, text, start_ms, end_ms }) => ({ id, speaker, text, start_ms, end_ms })) }) }),
  reviewInterview: (documentId: string, segmentsSha256: string) => request<InterviewDocument>(`/api/v1/analyst/interviews/${documentId}/review`, { method: 'POST', body: JSON.stringify({ expected_segments_sha256: segmentsSha256 }) }),
  deleteInterviewContent: (documentId: string) => request<InterviewDocument>(`/api/v1/analyst/interviews/${documentId}/content`, { method: 'DELETE' }),
  analyzeInterview: (documentId: string) => request<InterviewAnalysis>(`/api/v1/analyst/interviews/${documentId}/analysis`, { method: 'POST' }),
  proposeInterviewFacts: (analysisId: string, baseRevisionId: string, selectedFactIndices: number[]) =>
    request<InterviewProposalResponse>(`/api/v1/analyst/interview-analyses/${analysisId}/proposal`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId, selected_fact_indices: selectedFactIndices }),
    }),
  draftInterviewProcess: (analysisId: string, baseRevisionId: string) =>
    request<InterviewProposalResponse>(`/api/v1/analyst/interview-analyses/${analysisId}/process-draft`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId }),
    }),
  interviewEvidenceSummary: (sessionId: string) => request<import('./types').InterviewEvidenceSummary>(`/api/v1/analyst/sessions/${sessionId}/interview-evidence-summary`),
  crossInterviewConflicts: (sessionId: string) => request<import('./types').CrossInterviewConflictScan>(`/api/v1/analyst/sessions/${sessionId}/cross-interview-conflicts`),
  scanCrossInterviewConflicts: (sessionId: string) => request<import('./types').CrossInterviewConflictScan>(`/api/v1/analyst/sessions/${sessionId}/cross-interview-conflicts/scan`, { method: 'POST' }),
  resolveCrossInterviewConflict: (conflictId: string, action: 'confirm' | 'dismiss') => request<import('./types').CrossInterviewConflict>(`/api/v1/analyst/cross-interview-conflicts/${conflictId}/resolve`, { method: 'POST', body: JSON.stringify({ action }) }),
  draftMultiInterviewProcess: (sessionId: string, baseRevisionId: string) =>
    request<import('./types').MultiInterviewProposalResponse>(`/api/v1/analyst/sessions/${sessionId}/interview-process-draft`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId }),
    }),
  matchInterviewTemplate: (analysisId: string, locale: Locale, excludedIds: string[] = []) =>
    request<InterviewTemplateMatch>(`/api/v1/analyst/interview-analyses/${analysisId}/template-match`, {
      method: 'POST',
      body: JSON.stringify({ locale, excluded_ids: excludedIds }),
    }),
  acceptProposal: (proposalId: string, baseRevisionId: string) =>
    request<ProposedPatch>(`/api/v1/analyst/proposals/${proposalId}/accept`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId }),
    }),
  rejectProposal: (proposalId: string) =>
    request<ProposedPatch>(`/api/v1/analyst/proposals/${proposalId}/reject`, { method: 'POST' }),
  createProject: (workspaceId: string, name: string, locale: Locale, processIr: unknown, targetMode: 'process' | 'agent' = 'process') =>
    request<Project>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId, name, default_locale: locale, process_ir: processIr, target_mode: targetMode }),
    }),
  importN8n: (workspaceId: string, workflow: Record<string, unknown>, sourceMinor: '2.32' | '2.31' | '2.30', locale: Locale) =>
    request<N8nImportResult>('/api/v1/n8n-imports', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId, workflow, source_minor: sourceMinor, locale }),
    }),
  validatePythonCode: (processIr: ProcessIR, stepId: string, targetMinor: '2.32' | '2.31' | '2.30', customLogic: NonNullable<ProcessStep['customLogic']>) =>
    request<PythonCodeValidation>('/api/v1/exports/n8n/python-code/validate', {
      method: 'POST',
      body: JSON.stringify({ process_ir: processIr, step_id: stepId, target_minor: targetMinor, custom_logic: customLogic }),
    }),
  generatePythonCode: (processIr: ProcessIR, stepId: string, businessRuleId: string, reason: string, inputField: string, outputField: string, operator: '<' | '<=' | '==' | '!=' | '>=' | '>', threshold: number) =>
    request<PythonCodeGeneration>('/api/v1/exports/n8n/python-code/generate', {
      method: 'POST',
      body: JSON.stringify({ process_ir: processIr, step_id: stepId, business_rule_id: businessRuleId, reason, input_field: inputField, output_field: outputField, operator, threshold }),
    }),
  validateProjectArchive: (file: File) => request<ProjectArchiveValidation>('/api/v1/project-archives/validate', { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file }),
  restoreProjectArchive: (workspaceId: string, file: File) => request<ProjectArchiveRestore>(`/api/v1/project-archives/restore?workspaceId=${encodeURIComponent(workspaceId)}`, { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file }),
  applyTemplate: (projectId: string, templateId: string, baseRevisionId: string, locale: Locale) =>
    request<Project>(`/api/v1/projects/${projectId}/templates/${templateId}`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId, locale }),
    }),
  patchProject: (projectId: string, baseRevisionId: string, patch: Array<Record<string, unknown>>) =>
    request<Project>(`/api/v1/projects/${projectId}/revisions`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId, patch }),
    }),
  confirmClassification: (projectId: string, baseRevisionId: string, rubricVersion: string, entryIds: string[]) =>
    request<Project>(`/api/v1/projects/${projectId}/classification`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId, rubric_version: rubricVersion, entry_ids: entryIds }),
    }),
  undo: (projectId: string, baseRevisionId: string) =>
    request<Project>(`/api/v1/projects/${projectId}/undo`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId }),
    }),
  restore: (projectId: string, baseRevisionId: string, targetRevisionId: string) =>
    request<Project>(`/api/v1/projects/${projectId}/restore`, {
      method: 'POST',
      body: JSON.stringify({ base_revision_id: baseRevisionId, target_revision_id: targetRevisionId }),
    }),
  logout: async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN)
    try {
      if (refreshToken) {
        await request<void>('/api/v1/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
      }
    } finally {
      clearTokens()
    }
  },
}

export async function downloadProjectArchive(project: Project) {
  let token = localStorage.getItem(ACCESS_TOKEN)
  let response = await fetch(`/api/v1/project-archives/projects/${project.id}`, { headers: { Authorization: `Bearer ${token}` } })
  if (response.status === 401 && localStorage.getItem(REFRESH_TOKEN)) {
    token = await rotateTokens()
    response = await fetch(`/api/v1/project-archives/projects/${project.id}`, { headers: { Authorization: `Bearer ${token}` } })
  }
  if (!response.ok) throw await parseError(response)
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${project.id}-project-backup.apa.zip`
  anchor.click()
  URL.revokeObjectURL(url)
}

export type ExportFormat = 'spec' | 'bpmn' | 'n8n' | 'agent'
export type AppSpecTarget = 'cursor' | 'codex' | 'google_ai_studio' | 'bolt' | 'generic'
export type AgentTarget = 'openclaw' | 'hermes' | 'langgraph' | 'crewai' | 'agno'

function exportRequest(format: ExportFormat, n8nTarget: string, appTarget: AppSpecTarget, agentTarget: AgentTarget, locale: string, includeN8nGuide: boolean) {
  if (format === 'spec') return `/api/v1/exports/app-spec/${appTarget}?locale=${encodeURIComponent(locale)}`
  if (format === 'bpmn') return '/api/v1/exports/drawio'
  if (format === 'agent') return `/api/v1/exports/agent/${agentTarget}/package?locale=${encodeURIComponent(locale)}`
  return `/api/v1/exports/n8n/${n8nTarget}/package?locale=${encodeURIComponent(locale)}&includeGeneralGuide=${includeN8nGuide}`
}

function exportFilename(project: Project, format: ExportFormat, n8nTarget: string, appTarget: AppSpecTarget, agentTarget: AgentTarget) {
  const processId = project.current_revision.process_ir.process.id
  if (format === 'spec') return `${processId}-app-spec-${appTarget}.md`
  if (format === 'bpmn') return `${processId}-bpmn.drawio`
  if (format === 'agent') return `${processId}-agent-${agentTarget}.zip`
  return `${processId}-n8n-${n8nTarget}.zip`
}

export async function downloadExport(
  project: Project,
  format: ExportFormat,
  n8nTarget: string,
  appTarget: AppSpecTarget,
  agentTarget: AgentTarget,
  includeN8nGuide: boolean,
  roundTrip = false,
) {
  const path = format === 'n8n' && roundTrip
    ? `/api/v1/n8n-imports/projects/${project.id}/round-trip/${n8nTarget}/package`
    : exportRequest(format, n8nTarget, appTarget, agentTarget, project.default_locale, includeN8nGuide)
  const body = format === 'n8n' && roundTrip
    ? { revision_id: project.current_revision_id, locale: project.default_locale, include_general_guide: includeN8nGuide }
    : project.current_revision.process_ir
  const idempotencyKey = `${project.id}:${newIdempotencyKey('export')}`
  let token = localStorage.getItem(ACCESS_TOKEN)
  let response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
  if (response.status === 401 && localStorage.getItem(REFRESH_TOKEN)) {
    token = await rotateTokens()
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
    })
  }
  if (!response.ok) throw await parseError(response)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = exportFilename(project, format, n8nTarget, appTarget, agentTarget)
  anchor.click()
  URL.revokeObjectURL(url)
}
