import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Archive, ArchiveRestore, ArrowRight, BarChart3, Bot, CheckCircle2, ChevronDown, ChevronRight, CircleOff, Clock3, Copy, Crown, Download, FileArchive, FileJson, FolderKanban, FolderPlus, KeyRound, LayoutTemplate, LoaderCircle, LogOut, MonitorCog, Pencil, PlugZap, Plus, RotateCcw, Search, ShieldCheck, Star, Trash2, Upload, UserMinus, Users, Workflow, X } from 'lucide-react'
import { api, ApiError } from '../api'
import { createProcessTemplate } from '../process-template'
import type { AdminActivityReport, LLMConfiguration, LLMCredentialInput, LLMProvider, ProcessTemplate, Project, ProjectArchiveValidation, Readiness, Rubric, RuntimeConnectionInput, RuntimeConnectionProfile, TemplateCollection, TemplateCollectionItem, User, WorkspaceAuditEvent, WorkspaceInvitation, WorkspaceMember } from '../types'
import { useI18n } from '../i18n/context'
import { Brand } from './Brand'
import { LanguageSwitch } from './LanguageSwitch'

interface ProjectRow extends Project { readinessScore?: number }

export function ProjectsScreen({ user, invitationNotice, onOpen, onAdmin, onLogout }: { user: User; invitationNotice?: 'accepted' | 'error' | null; onOpen: (id: string) => void; onAdmin?: () => void; onLogout: () => void }) {
  const { locale, t } = useI18n()
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showArchiveImport, setShowArchiveImport] = useState(false)
  const [showConnections, setShowConnections] = useState(false)
  const [showLlmSettings, setShowLlmSettings] = useState(false)
  const [showWorkspaceRename, setShowWorkspaceRename] = useState(false)
  const [showWorkspaceCreate, setShowWorkspaceCreate] = useState(false)
  const [showWorkspaceMembers, setShowWorkspaceMembers] = useState(false)
  const [showWorkspaceReport, setShowWorkspaceReport] = useState(false)
  const [showArchivedWorkspaces, setShowArchivedWorkspaces] = useState(false)
  const [workspaces, setWorkspaces] = useState(user.workspaces)
  const activeWorkspaces = workspaces.filter((item) => item.status !== 'archived')
  const archivedWorkspaces = workspaces.filter((item) => item.status === 'archived')
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(user.active_workspace_id ?? user.workspaces.find((item) => item.status !== 'archived')?.workspace_id ?? '')
  const activeWorkspace = activeWorkspaces.find((item) => item.workspace_id === activeWorkspaceId) ?? activeWorkspaces[0]
  const [llmConfiguration, setLlmConfiguration] = useState<LLMConfiguration | null>(null)
  const [templates, setTemplates] = useState<ProcessTemplate[]>([])
  const [rubric, setRubric] = useState<Rubric | null>(null)
  const [collections, setCollections] = useState<TemplateCollection[]>([])
  const [collectionItems, setCollectionItems] = useState<TemplateCollectionItem[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(true)
  const [selectedTemplateId, setSelectedTemplateId] = useState('blank')
  const [templateSearch, setTemplateSearch] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    if (!activeWorkspaceId) { setProjects([]); setLoading(false); return }
    setLoading(true)
    api.projects(activeWorkspaceId).then(async (items) => {
      const scores = await Promise.all(items.map((item) => api.readiness(item.id).catch(() => null)))
      if (active) setProjects(items.map((item, index) => ({ ...item, readinessScore: (scores[index] as Readiness | null)?.overall })))
    }).catch((reason) => active && setError(reason instanceof ApiError ? reason.message : t('error')))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [activeWorkspaceId, t])

  useEffect(() => {
    let active = true
    api.llmConfiguration().then((value) => active && setLlmConfiguration(value)).catch(() => undefined)
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setTemplatesLoading(true)
    Promise.all([api.templates(locale), api.userTemplates(locale), api.rubric(locale), api.templateCollections(), api.templateCollectionItems()])
      .then(([catalog, personal, rubricResult, nextCollections, nextItems]) => { if (active) { setTemplates([...personal, ...catalog]); setRubric(rubricResult); setCollections(nextCollections); setCollectionItems(nextItems) } })
      .catch(() => active && setError(t('templateLoadError')))
      .finally(() => active && setTemplatesLoading(false))
    return () => { active = false }
  }, [locale, t])

  const filtered = useMemo(() => projects.filter((project) => project.name.toLowerCase().includes(search.toLowerCase())), [projects, search])

  async function createProject(event: FormEvent) {
    event.preventDefault()
    const workspace = activeWorkspace
    if (!workspace) return
    setBusy(true)
    setError('')
    try {
      const selectedSummary = templates.find((item) => item.id === selectedTemplateId)
      const selected = selectedSummary?.source === 'user' ? selectedSummary : selectedSummary ? await api.template(selectedSummary.id, locale) : null
      const processIr = selected?.process_ir ?? createProcessTemplate(name, locale)
      const project = await api.createProject(workspace.workspace_id, name, locale, processIr, selected?.agent_enabled ? 'agent' : 'process')
      onOpen(project.id)
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : t('error'))
    } finally {
      setBusy(false)
    }
  }

  function openCreate() {
    setName('')
    setSelectedTemplateId('blank')
    setTemplateSearch('')
    setShowCreate(true)
  }

  async function createCollection(collectionName: string) {
    const created = await api.createTemplateCollection(collectionName)
    setCollections((current) => [...current, created])
  }

  async function renameWorkspace(nextName: string) {
    const workspace = activeWorkspace
    if (!workspace) return
    setBusy(true); setError('')
    try {
      const renamed = await api.renameWorkspace(workspace.workspace_id, nextName)
      setWorkspaces((current) => current.map((item) => item.workspace_id === workspace.workspace_id ? { ...item, workspace_name: renamed.name } : item))
      setShowWorkspaceRename(false)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  async function createWorkspace(nextName: string) {
    setBusy(true); setError('')
    try {
      const created = await api.createWorkspace(nextName, locale)
      setWorkspaces((current) => [...current, created])
      setActiveWorkspaceId(created.workspace_id)
      setShowWorkspaceCreate(false)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  async function switchWorkspace(workspaceId: string) {
    if (workspaceId === activeWorkspaceId) return
    setError('')
    try {
      await api.activateWorkspace(workspaceId)
      setActiveWorkspaceId(workspaceId)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
  }

  async function refreshWorkspaces() {
    const next = await api.me()
    setWorkspaces(next.workspaces)
    setActiveWorkspaceId(next.active_workspace_id ?? next.workspaces.find((item) => item.status !== 'archived')?.workspace_id ?? '')
  }

  async function toggleCollection(template: ProcessTemplate, collectionId: string, included: boolean) {
    if (included) await api.removeTemplateFromCollection(collectionId, template.source, template.id)
    else await api.addTemplateToCollection(collectionId, template.source, template.id)
    setCollectionItems((current) => included
      ? current.filter((item) => !(item.collection_id === collectionId && item.template_source === template.source && item.template_id === template.id))
      : [...current, { collection_id: collectionId, template_source: template.source, template_id: template.id }])
    setCollections((current) => current.map((collection) => collection.id === collectionId ? { ...collection, item_count: Math.max(0, collection.item_count + (included ? -1 : 1)) } : collection))
  }

  async function importN8n(workflow: Record<string, unknown>, minor: '2.32' | '2.31' | '2.30') {
    const workspace = activeWorkspace
    if (!workspace) return
    setBusy(true); setError('')
    try {
      const result = await api.importN8n(workspace.workspace_id, workflow, minor, locale)
      sessionStorage.setItem(`apa_n8n_import_report_${result.project.id}`, JSON.stringify(result))
      setShowImport(false)
      onOpen(result.project.id)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  return (
    <div className="app-shell">
      <aside className="global-sidebar">
        <Brand compact />
        <nav>
          <button className="nav-button is-active" title={t('projects')}><FolderKanban size={19} /><span>{t('projects')}</span></button>
          <button className="nav-button" data-help-topic="templates" onClick={openCreate} title={t('templates')}><LayoutTemplate size={19} /><span>{t('templates')}</span></button>
          <button className="nav-button" data-help-topic="connections" onClick={() => setShowConnections(true)} title={t('connections')}><PlugZap size={19} /><span>{t('connections')}</span></button>
          {llmConfiguration?.deployment_profile.credential_management_enabled && <button className="nav-button" onClick={() => setShowLlmSettings(true)} title={t('llmSettings')}><KeyRound size={19} /><span>{t('llmSettings')}</span></button>}
          {onAdmin && <button className="nav-button" onClick={onAdmin} title={t('admin')}><ShieldCheck size={19} /><span>{t('admin')}</span></button>}
        </nav>
        <button className="nav-button global-sidebar__logout" onClick={onLogout} title={t('logout')}><LogOut size={19} /><span>{t('logout')}</span></button>
      </aside>
      <main className="projects-page" data-help-topic="projects">
        <header className="topbar projects-topbar">
          <div><span className="eyebrow">{t('workspace')}</span><div className="workspace-name" data-help-topic="workspace"><select value={activeWorkspace?.workspace_id ?? ''} onChange={(event) => void switchWorkspace(event.target.value)} aria-label={t('switchWorkspace')}>{activeWorkspaces.length === 0 && <option value="">{t('noActiveWorkspace')}</option>}{activeWorkspaces.map((workspace) => <option value={workspace.workspace_id} key={workspace.workspace_id}>{workspace.workspace_name}</option>)}</select>{activeWorkspace && <button className="icon-button workspace-members-button" onClick={() => setShowWorkspaceMembers(true)} title={t('workspaceMembers')} aria-label={t('workspaceMembers')}><Users size={16} /></button>}{activeWorkspace && <button className="icon-button" onClick={() => setShowWorkspaceReport(true)} title={t('adminReports')} aria-label={t('adminReports')}><BarChart3 size={16} /></button>}{activeWorkspace?.role === 'owner' && <button className="icon-button workspace-rename-button" onClick={() => setShowWorkspaceRename(true)} title={t('renameWorkspace')} aria-label={t('renameWorkspace')}><Pencil size={15} /></button>}{archivedWorkspaces.length > 0 && <button className="icon-button" onClick={() => setShowArchivedWorkspaces(true)} title={t('archivedWorkspaces')} aria-label={t('archivedWorkspaces')}><ArchiveRestore size={16} /></button>}<button className="icon-button" onClick={() => setShowWorkspaceCreate(true)} title={t('createWorkspace')} aria-label={t('createWorkspace')}><Plus size={16} /></button></div></div>
          <div className="topbar__actions"><LanguageSwitch />{llmConfiguration?.deployment_profile.credential_management_enabled && <button className="icon-button" onClick={() => setShowLlmSettings(true)} title={t('llmSettings')} aria-label={t('llmSettings')}><KeyRound size={18} /></button>}<button className="icon-button" data-help-topic="connections" onClick={() => setShowConnections(true)} title={t('connections')} aria-label={t('connections')} disabled={!activeWorkspace}><PlugZap size={18} /></button><button className="icon-button" data-help-topic="backup" onClick={() => setShowArchiveImport(true)} title={t('restoreBackup')} aria-label={t('restoreBackup')} disabled={!activeWorkspace}><ArchiveRestore size={18} /></button><button className="button button--secondary" data-help-topic="import" onClick={() => setShowImport(true)} disabled={!activeWorkspace}><Upload size={17} />{t('importN8n')}</button><button className="button button--primary" data-help-topic="new_project" onClick={openCreate} disabled={!activeWorkspace}><Plus size={17} />{t('newProject')}</button></div>
        </header>
        <section className="projects-content">
          <div className="section-heading"><div><span className="section-label">{t('allProcesses')}</span><h2>{t('projects')}</h2></div><span className="count-badge">{projects.length}</span></div>
          <label className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`${t('name')}…`} /></label>
          {invitationNotice && <div className={`notice ${invitationNotice === 'error' ? 'notice--error' : 'notice--success'}`}>{t(invitationNotice === 'accepted' ? 'workspaceInvitationAccepted' : 'workspaceInvitationFailed')}</div>}
          {error && <div className="notice notice--error">{error}</div>}
          {!activeWorkspace && <div className="notice"><strong>{t('noActiveWorkspace')}</strong> {t('noActiveWorkspaceHint')} <button className="button button--secondary button--compact" onClick={() => setShowWorkspaceCreate(true)}><Plus size={15} />{t('createWorkspace')}</button></div>}
          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} />{t('loading')}</div> : filtered.length === 0 ? (
            <div className="empty-state"><span className="empty-state__icon"><FolderKanban size={25} /></span><h3>{t('noProjects')}</h3><p>{t('noProjectsText')}</p><button className="button button--primary" onClick={openCreate}><Plus size={17} />{t('newProject')}</button></div>
          ) : (
            <div className="project-table" role="table">
              <div className="project-table__head" role="row"><span>{t('name')}</span><span>{t('readiness')}</span><span>{t('version')}</span><span>{t('updated')}</span><span /></div>
              {filtered.map((project) => (
                <button className="project-row" key={project.id} onClick={() => onOpen(project.id)} role="row">
                  <span className="project-cell project-cell--name"><span className="project-icon"><Workflow size={18} /></span><span><strong>{project.name}</strong><small>{project.current_revision.process_ir.process.description || t('noDescription')}</small></span></span>
                  <span className="readiness-cell"><span className="mini-progress"><i style={{ width: `${project.readinessScore ?? 0}%` }} /></span><strong>{project.readinessScore ?? '—'}%</strong></span>
                  <span>v{project.current_revision.version_number}</span>
                  <span className="date-cell"><Clock3 size={14} />{new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(new Date(project.updated_at))}</span>
                  <span className="row-action"><ArrowRight size={18} /></span>
                </button>
              ))}
            </div>
          )}
        </section>
      </main>
      {showCreate && <TemplateCreateModal
        templates={templates} rubric={rubric} collections={collections} collectionItems={collectionItems} loading={templatesLoading} selectedId={selectedTemplateId} search={templateSearch}
        name={name} busy={busy} onName={setName} onSearch={setTemplateSearch}
        onSelect={(template) => { setSelectedTemplateId(template?.id ?? 'blank'); setName(template?.name ?? '') }}
        onCreateCollection={createCollection} onToggleCollection={toggleCollection}
        onClose={() => setShowCreate(false)} onSubmit={createProject}
      />}
      {showImport && <N8nImportModal busy={busy} onClose={() => setShowImport(false)} onImport={importN8n} />}
      {showArchiveImport && <ArchiveImportModal workspaceId={activeWorkspace?.workspace_id ?? ''} busy={busy} setBusy={setBusy} onClose={() => setShowArchiveImport(false)} onRestored={(project) => { setShowArchiveImport(false); onOpen(project.id) }} />}
      {showConnections && activeWorkspace && <RuntimeConnectionsModal workspaceId={activeWorkspace.workspace_id} canManage={activeWorkspace.role === 'owner'} onClose={() => setShowConnections(false)} />}
      {showLlmSettings && <LlmSettingsModal onClose={() => setShowLlmSettings(false)} />}
      {showWorkspaceRename && activeWorkspace && <WorkspaceNameModal title={t('renameWorkspace')} hint={t('renameWorkspaceHint')} initialName={activeWorkspace.workspace_name} busy={busy} onClose={() => setShowWorkspaceRename(false)} onSave={renameWorkspace} />}
      {showWorkspaceReport && activeWorkspace && <WorkspaceActivityReportModal workspaceId={activeWorkspace.workspace_id} workspaceName={activeWorkspace.workspace_name} onClose={() => setShowWorkspaceReport(false)} />}
      {showWorkspaceCreate && <WorkspaceNameModal title={t('createWorkspace')} hint={t('createWorkspaceHint')} initialName="" busy={busy} onClose={() => setShowWorkspaceCreate(false)} onSave={createWorkspace} />}
      {showWorkspaceMembers && activeWorkspace && <WorkspaceMembersModal workspaceId={activeWorkspace.workspace_id} workspaceName={activeWorkspace.workspace_name} currentUserId={user.id} canManage={activeWorkspace.role === 'owner'} onClose={() => setShowWorkspaceMembers(false)} onMembershipChanged={refreshWorkspaces} onArchived={async () => { await refreshWorkspaces(); setShowWorkspaceMembers(false) }} />}
      {showArchivedWorkspaces && <ArchivedWorkspacesModal workspaces={archivedWorkspaces} onClose={() => setShowArchivedWorkspaces(false)} onRestored={refreshWorkspaces} />}
    </div>
  )
}

function WorkspaceActivityReportModal({ workspaceId, workspaceName, onClose }: { workspaceId: string; workspaceName: string; onClose: () => void }) {
  const { locale, t } = useI18n()
  const [report, setReport] = useState<AdminActivityReport | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api.workspaceActivityReport(workspaceId).then((value) => active && setReport(value)).catch((reason) => active && setError(reason instanceof ApiError ? reason.message : t('error')))
    return () => { active = false }
  }, [t, workspaceId])
  const number = (value: number) => new Intl.NumberFormat(locale).format(value)
  const downloadCsv = () => {
    if (!report) return
    const item = report.workspaces[0]
    const csv = `metric,value\nworkflows_created,${item.workflowsCreated}\nworkflows_ready,${item.workflowsReady}\nworkflows_in_progress,${item.workflowsInProgress}\nn8n_publications,${item.n8nPublications}\nagent_deliveries,${item.agentDeliveries}\nagent_runs,${item.agentRuns}\ninput_tokens,${item.inputTokens}\noutput_tokens,${item.outputTokens}\ntotal_tokens,${item.totalTokens}\nestimated_cost_usd,${item.estimatedCostPicousd / 1_000_000_000_000}\n`
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `workspace-report-${report.periodStart.slice(0, 10)}.csv`; link.click(); URL.revokeObjectURL(url)
  }
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal workspace-report-modal"><div className="modal__header"><div><span className="section-label">{workspaceName}</span><h2>{t('adminActivityReport')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div>{error && <div className="notice notice--error">{error}</div>}{!report ? <div className="loading-state"><LoaderCircle className="spin" size={20} />{t('loading')}</div> : <><p className="modal__description">{new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(report.periodStart))} - {new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(report.periodEnd))}</p><div className="workspace-report-grid"><span><small>{t('adminWorkflowsCreated')}</small><strong>{number(report.summary.workflowsCreated)}</strong></span><span><small>{t('adminReady')}</small><strong>{number(report.summary.workflowsReady)}</strong></span><span><small>{t('adminInProgress')}</small><strong>{number(report.summary.workflowsInProgress)}</strong></span><span><small>n8n</small><strong>{number(report.summary.n8nPublications)}</strong></span><span><small>{t('adminAgents')}</small><strong>{number(report.summary.agentDeliveries)}</strong></span><span><small>{t('adminTokensSpent')}</small><strong>{number(report.summary.totalTokens)}</strong></span></div><div className="modal__actions"><button className="button button--secondary" onClick={downloadCsv}><Download size={16} />{t('adminDownloadCsv')}</button><button className="button button--primary" onClick={onClose}>{t('close')}</button></div></>}</div></div>
}

function WorkspaceMembersModal({ workspaceId, workspaceName, currentUserId, canManage, onClose, onMembershipChanged, onArchived }: { workspaceId: string; workspaceName: string; currentUserId: string; canManage: boolean; onClose: () => void; onMembershipChanged: () => Promise<void>; onArchived: () => Promise<void> }) {
  const { locale, t } = useI18n()
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([])
  const [auditEvents, setAuditEvents] = useState<WorkspaceAuditEvent[]>([])
  const [email, setEmail] = useState('')
  const [invitationLink, setInvitationLink] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy(true); setError('')
    try {
      const [nextMembers, nextInvitations, nextAudit] = await Promise.all([api.workspaceMembers(workspaceId), canManage ? api.workspaceInvitations(workspaceId) : Promise.resolve([]), canManage ? api.workspaceAuditEvents(workspaceId) : Promise.resolve([])])
      setMembers(nextMembers); setInvitations(nextInvitations); setAuditEvents(nextAudit)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }, [canManage, t, workspaceId])

  useEffect(() => { void load() }, [load])

  async function invite(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setInvitationLink('')
    try {
      const created = await api.createWorkspaceInvitation(workspaceId, email.trim())
      setInvitationLink(`${window.location.origin}/?workspace_invitation=${encodeURIComponent(created.acceptanceToken)}`)
      setEmail(''); await load()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  async function updateRole(member: WorkspaceMember, role: 'owner' | 'member') {
    setBusy(true); setError('')
    try { await api.updateWorkspaceMemberRole(workspaceId, member.userId, role); await load(); await onMembershipChanged() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  async function transfer(member: WorkspaceMember) {
    if (!window.confirm(t('transferOwnershipConfirm'))) return
    setBusy(true); setError('')
    try { await api.transferWorkspaceOwnership(workspaceId, member.userId); await load(); await onMembershipChanged() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  async function remove(member: WorkspaceMember) {
    if (!window.confirm(member.userId === currentUserId ? t('leaveWorkspaceConfirm') : t('removeMemberConfirm'))) return
    setBusy(true); setError('')
    try { await api.removeWorkspaceMember(workspaceId, member.userId); await onMembershipChanged(); if (member.userId === currentUserId) onClose(); else await load() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  async function revoke(invitation: WorkspaceInvitation) {
    setBusy(true); setError('')
    try { await api.revokeWorkspaceInvitation(workspaceId, invitation.id); await load() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  async function archive() {
    if (!window.confirm(t('archiveWorkspaceConfirm'))) return
    setBusy(true); setError('')
    try { await api.archiveWorkspace(workspaceId); await onArchived() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')); setBusy(false) }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal workspace-members-modal"><div className="modal__header"><div><span className="section-label">{workspaceName}</span><h2>{t('workspaceMembers')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{canManage ? t('workspaceMembersOwnerHint') : t('workspaceMembersHint')}</p>{error && <div className="notice notice--error">{error}</div>}{canManage && <form className="workspace-invite-form" onSubmit={invite}><label>{t('inviteByEmail')}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" required /></label><button className="button button--primary" disabled={busy || !email.trim()}><Plus size={16} />{t('invite')}</button></form>}{invitationLink && <div className="invitation-link"><div><strong>{t('invitationLink')}</strong><small>{t('invitationLinkHint')}</small></div><code>{invitationLink}</code><button className="icon-button" onClick={() => void navigator.clipboard.writeText(invitationLink)} title={t('copyLink')} aria-label={t('copyLink')}><Copy size={17} /></button></div>}{busy && members.length === 0 ? <div className="loading-state"><LoaderCircle className="spin" size={20} />{t('loading')}</div> : <div className="workspace-member-list">{members.map((member) => <div className="workspace-member" key={member.userId}><span className="workspace-member__avatar">{member.email.slice(0, 1).toUpperCase()}</span><span className="workspace-member__identity"><strong>{member.email}{member.userId === currentUserId ? ` · ${t('you')}` : ''}</strong><small>{new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(member.joinedAt))}</small></span><span className={`status-badge ${member.role === 'owner' ? 'is-active' : ''}`}>{member.role === 'owner' && <Crown size={13} />}{t(member.role === 'owner' ? 'workspaceOwner' : 'workspaceMember')}</span>{canManage && member.userId !== currentUserId && <div className="workspace-member__actions"><select value={member.role} onChange={(event) => void updateRole(member, event.target.value as 'owner' | 'member')} aria-label={t('workspaceRole')} disabled={busy}><option value="member">{t('workspaceMember')}</option><option value="owner">{t('workspaceOwner')}</option></select><button className="icon-button" onClick={() => void transfer(member)} title={t('transferOwnership')} aria-label={t('transferOwnership')} disabled={busy}><Crown size={16} /></button><button className="icon-button icon-button--danger" onClick={() => void remove(member)} title={t('removeMember')} aria-label={t('removeMember')} disabled={busy}><UserMinus size={16} /></button></div>}{member.userId === currentUserId && <button className="button button--secondary button--compact" onClick={() => void remove(member)} disabled={busy}><LogOut size={15} />{t('leaveWorkspace')}</button>}</div>)}</div>}{canManage && invitations.some((item) => item.status === 'pending') && <section className="workspace-invitations"><h3>{t('pendingInvitations')}</h3>{invitations.filter((item) => item.status === 'pending').map((invitation) => <div key={invitation.id}><span><strong>{invitation.email}</strong><small>{t('validUntil')} {new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(invitation.expiresAt))}</small></span><button className="icon-button icon-button--danger" onClick={() => void revoke(invitation)} title={t('revokeInvitation')} aria-label={t('revokeInvitation')}><Trash2 size={16} /></button></div>)}</section>}{canManage && auditEvents.length > 0 && <section className="workspace-audit"><h3>{t('workspaceAudit')}</h3>{auditEvents.slice(0, 8).map((event) => <div key={event.id}><strong>{workspaceAuditLabel(event.action, t)}</strong><time>{new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.createdAt))}</time></div>)}</section>}<div className="modal__actions modal__actions--split">{canManage && <button className="button button--danger" onClick={() => void archive()} disabled={busy}><Archive size={16} />{t('archiveWorkspace')}</button>}<button className="button button--secondary" onClick={onClose}>{t('close')}</button></div></div></div>
}

function workspaceAuditLabel(action: string, t: ReturnType<typeof useI18n>['t']) {
  const labels: Record<string, Parameters<typeof t>[0]> = {
    'workspace.created': 'auditWorkspaceCreated', 'workspace.renamed': 'auditWorkspaceRenamed',
    'workspace.invitation_created': 'auditInvitationCreated', 'workspace.invitation_revoked': 'auditInvitationRevoked',
    'workspace.invitation_accepted': 'auditInvitationAccepted', 'workspace.member_role_updated': 'auditRoleUpdated',
    'workspace.ownership_transferred': 'auditOwnershipTransferred', 'workspace.member_removed': 'auditMemberRemoved',
    'workspace.archived': 'auditWorkspaceArchived', 'workspace.restored': 'auditWorkspaceRestored',
    'workspace.commercial_state_updated': 'auditWorkspacePlanUpdated', 'billing.subscription_updated': 'auditSubscriptionUpdated',
  }
  return labels[action] ? t(labels[action]) : action
}

function ArchivedWorkspacesModal({ workspaces, onClose, onRestored }: { workspaces: User['workspaces']; onClose: () => void; onRestored: () => Promise<void> }) {
  const { locale, t } = useI18n()
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')
  async function restore(workspaceId: string) {
    setBusyId(workspaceId); setError('')
    try { await api.restoreWorkspace(workspaceId); await onRestored(); if (workspaces.length === 1) onClose() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusyId('') }
  }
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal modal--small"><div className="modal__header"><div><span className="section-label">{t('workspace')}</span><h2>{t('archivedWorkspaces')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{t('archivedWorkspacesHint')}</p>{error && <div className="notice notice--error">{error}</div>}<div className="archived-workspace-list">{workspaces.map((workspace) => <div key={workspace.workspace_id}><span><strong>{workspace.workspace_name}</strong><small>{workspace.archived_at ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(workspace.archived_at)) : ''}</small></span><button className="button button--secondary button--compact" onClick={() => void restore(workspace.workspace_id)} disabled={Boolean(busyId)}>{busyId === workspace.workspace_id ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />}{t('restoreWorkspace')}</button></div>)}</div><div className="modal__actions"><button className="button button--secondary" onClick={onClose}>{t('close')}</button></div></div></div>
}

function WorkspaceNameModal({ title, hint, initialName, busy, onClose, onSave }: { title: string; hint: string; initialName: string; busy: boolean; onClose: () => void; onSave: (name: string) => Promise<void> }) {
  const { t } = useI18n()
  const [name, setName] = useState(initialName)
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><form className="modal modal--small" onSubmit={(event) => { event.preventDefault(); void onSave(name) }}><div className="modal__header"><div><span className="section-label">{t('workspace')}</span><h2>{title}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{hint}</p><label className="field-label">{t('workspaceName')}<input autoFocus value={name} onChange={(event) => setName(event.target.value)} minLength={1} maxLength={120} required /></label><div className="modal__actions"><button type="button" className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={busy || !name.trim()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Pencil size={16} />}{t('saveChanges')}</button></div></form></div>
}

const providerModels: Record<LLMProvider, string> = { deepseek: 'deepseek-chat', openai: 'gpt-5-mini', openai_compatible: '' }

function LlmSettingsModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const [configuration, setConfiguration] = useState<LLMConfiguration | null>(null)
  const [provider, setProvider] = useState<LLMProvider>('deepseek')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState(providerModels.deepseek)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setError('')
    try {
      const next = await api.llmConfiguration()
      setConfiguration(next)
      const selected = next.selected_provider ?? next.providers[0]?.id
      if (selected) chooseProvider(selected, next)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
  }

  useEffect(() => {
    let active = true
    api.llmConfiguration().then((next) => {
      if (!active) return
      setConfiguration(next)
      const selected = next.selected_provider ?? next.providers[0]?.id
      if (!selected) return
      const existing = next.credentials.find((item) => item.provider === selected)
      setProvider(selected)
      setApiKey('')
      setBaseUrl(existing?.base_url ?? next.providers.find((item) => item.id === selected)?.default_base_url ?? '')
      setModel(existing?.model ?? providerModels[selected])
    }).catch(() => undefined)
    return () => { active = false }
  }, [])

  function chooseProvider(next: LLMProvider, source = configuration) {
    const existing = source?.credentials.find((item) => item.provider === next)
    setProvider(next)
    setApiKey('')
    setBaseUrl(existing?.base_url ?? source?.providers.find((item) => item.id === next)?.default_base_url ?? '')
    setModel(existing?.model ?? providerModels[next])
  }

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const input: LLMCredentialInput = { provider, api_key: apiKey || null, base_url: baseUrl, model }
      await api.saveLlmCredential(input)
      await api.selectLlmProvider(provider)
      await load()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  async function remove(itemProvider: LLMProvider) {
    setBusy(true); setError('')
    try { await api.deleteLlmCredential(itemProvider); await load() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal runtime-connections-modal">
    <div className="modal__header"><div><span className="section-label">LLM</span><h2>{t('llmSettings')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div>
    <p className="modal__description">{configuration && !configuration.deployment_profile.credential_management_enabled ? t('llmManagedHint') : t('llmSettingsHint')}</p>
    {error && <div className="notice notice--error">{error}</div>}
    {!configuration ? <div className="loading-state"><LoaderCircle className="spin" size={18} />{t('loading')}</div> : !configuration.deployment_profile.credential_management_enabled ? <div className="runtime-empty"><KeyRound size={22} /><strong>{t('llmManaged')}</strong><span>{t('llmManagedHint')}</span></div> : <>
      {!configuration.encryption_configured && <div className="notice notice--error">{t('llmEncryptionMissing')}</div>}
      <div className="runtime-list">{configuration.credentials.map((item) => <article className="runtime-profile" key={item.provider}><div className="runtime-profile__main"><span className={`runtime-status ${item.selected ? 'runtime-status--verified' : ''}`}>{item.selected && <CheckCircle2 size={15} />}{item.selected ? t('llmSelected') : t('llmConfigured')}</span><strong>{t(`llmProvider_${item.provider}`)}</strong><span>{item.model}</span><small>{item.base_url}</small></div><div className="runtime-profile__actions">{!item.selected && <button className="button button--secondary button--small" disabled={busy} onClick={async () => { setBusy(true); await api.selectLlmProvider(item.provider); await load(); setBusy(false) }}>{t('llmUseProvider')}</button>}<button className="icon-button" onClick={() => chooseProvider(item.provider)} title={t('editConnection')}><Pencil size={15} /></button><button className="icon-button icon-button--danger" disabled={busy} onClick={() => void remove(item.provider)} title={t('deleteConnection')}><Trash2 size={15} /></button></div></article>)}</div>
      <form className="runtime-form" onSubmit={save}><h3>{t('llmAddOrUpdate')}</h3><div className="runtime-form__grid"><label>{t('llmProvider')}<select value={provider} onChange={(event) => chooseProvider(event.target.value as LLMProvider)}>{configuration.providers.map((item) => <option value={item.id} key={item.id}>{t(`llmProvider_${item.id}`)}</option>)}</select></label><label>{t('llmModel')}<input value={model} onChange={(event) => setModel(event.target.value)} required /></label>{provider === 'openai_compatible' && <label className="runtime-form__wide">{t('llmEndpoint')}<input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="http://ollama:11434/v1" required /></label>}<label className="runtime-form__wide">{t('llmApiKey')}<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={configuration.credentials.some((item) => item.provider === provider && item.key_configured) ? t('llmKeyStored') : ''} /></label></div><p className="runtime-form__hint">{t('llmKeyHint')}</p><div className="modal__actions"><button className="button button--primary" disabled={busy || !configuration.encryption_configured}>{busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />}{t('saveChanges')}</button></div></form>
    </>}
  </div></div>
}

const emptyRuntimeInput: RuntimeConnectionInput = { name: '', kind: 'n8n', endpoint_url: '', secret_ref: 'env:', n8n_minor: '2.32' }

function RuntimeConnectionsModal({ workspaceId, canManage, onClose }: { workspaceId: string; canManage: boolean; onClose: () => void }) {
  const { locale, t } = useI18n()
  const [profiles, setProfiles] = useState<RuntimeConnectionProfile[]>([])
  const [input, setInput] = useState<RuntimeConnectionInput>(emptyRuntimeInput)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.runtimeConnections(workspaceId).then((items) => active && setProfiles(items)).catch((reason) => active && setError(reason instanceof ApiError ? reason.message : t('error'))).finally(() => active && setLoading(false))
    return () => { active = false }
  }, [workspaceId, t])

  function resetForm() { setInput(emptyRuntimeInput); setEditingId(null) }
  function edit(profile: RuntimeConnectionProfile) {
    setEditingId(profile.id)
    setInput({ name: profile.name, kind: profile.kind, endpoint_url: profile.endpoint_url, secret_ref: profile.secret_ref, n8n_minor: profile.n8n_minor })
  }
  function replace(updated: RuntimeConnectionProfile) { setProfiles((current) => current.map((item) => item.id === updated.id ? updated : item)) }

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusyId('form')
    try {
      const normalized = { ...input, secret_ref: input.secret_ref.startsWith('env:') ? input.secret_ref : `env:${input.secret_ref}` }
      const profile = editingId ? await api.updateRuntimeConnection(editingId, normalized) : await api.createRuntimeConnection(workspaceId, normalized)
      if (editingId) replace(profile); else setProfiles((current) => [...current, profile].sort((a, b) => a.name.localeCompare(b.name)))
      resetForm()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusyId(null) }
  }

  async function act(profileId: string, action: 'verify' | 'disable' | 'delete') {
    setBusyId(profileId); setError('')
    try {
      if (action === 'delete') { await api.deleteRuntimeConnection(profileId); setProfiles((current) => current.filter((item) => item.id !== profileId)); if (editingId === profileId) resetForm() }
      else if (action === 'disable') replace(await api.disableRuntimeConnection(profileId))
      else replace((await api.verifyRuntimeConnection(profileId)).profile)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusyId(null) }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal runtime-connections-modal">
    <div className="modal__header"><div><span className="section-label">RUNTIME</span><h2>{t('connections')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div>
    <p className="modal__description">{t('connectionsHint')}</p>
    {error && <div className="notice notice--error">{error}</div>}
    {loading ? <div className="loading-state"><LoaderCircle className="spin" size={18} />{t('loading')}</div> : profiles.length === 0 ? <div className="runtime-empty"><PlugZap size={22} /><strong>{t('noConnections')}</strong><span>{t('noConnectionsHint')}</span></div> : <div className="runtime-list">{profiles.map((profile) => <article className="runtime-profile" key={profile.id}>
      <div className="runtime-profile__main"><span className={`runtime-status runtime-status--${profile.status}`}>{profile.status === 'verified' ? <CheckCircle2 size={15} /> : profile.status === 'disabled' ? <CircleOff size={15} /> : <PlugZap size={15} />}{t(`connectionStatus_${profile.status}`)}</span><strong>{profile.name}</strong><span>{profile.kind === 'n8n' ? `n8n ${profile.n8n_minor}` : profile.kind}</span><small>{profile.endpoint_url}</small>{profile.last_checked_at && <small>{t('lastChecked')}: {new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(profile.last_checked_at))}{profile.detected_version ? ` · ${profile.detected_version}` : ''}</small>}{profile.last_check_code && profile.status === 'failed' && <small className="runtime-profile__error">{t(`connectionResult_${profile.last_check_code}` as Parameters<typeof t>[0])}</small>}</div>
      {canManage && <div className="runtime-profile__actions"><button className="icon-button" onClick={() => edit(profile)} title={t('editConnection')} aria-label={t('editConnection')}><Pencil size={15} /></button><button className="button button--secondary button--small" disabled={busyId === profile.id} onClick={() => void act(profile.id, 'verify')}>{busyId === profile.id ? <LoaderCircle className="spin" size={14} /> : <PlugZap size={14} />}{t('checkConnection')}</button>{profile.status !== 'disabled' && <button className="icon-button" onClick={() => void act(profile.id, 'disable')} title={t('disableConnection')} aria-label={t('disableConnection')}><CircleOff size={15} /></button>}<button className="icon-button icon-button--danger" onClick={() => void act(profile.id, 'delete')} title={t('deleteConnection')} aria-label={t('deleteConnection')}><Trash2 size={15} /></button></div>}
    </article>)}</div>}
    {canManage ? <form className="runtime-form" onSubmit={submit}><h3>{editingId ? t('editConnection') : t('addConnection')}</h3><div className="runtime-form__grid"><label>{t('connectionName')}<input value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} required maxLength={160} /></label><label>{t('connectionType')}<select value={input.kind} onChange={(event) => { const kind = event.target.value as RuntimeConnectionInput['kind']; setInput({ ...input, kind, n8n_minor: kind === 'n8n' ? '2.32' : null }) }}><option value="n8n">n8n</option><option value="openclaw">OpenClaw</option><option value="hermes">Hermes</option></select></label><label className="runtime-form__wide">{t('connectionAddress')}<input type="url" value={input.endpoint_url} onChange={(event) => setInput({ ...input, endpoint_url: event.target.value })} placeholder="https://automation.example.com" required /></label><label>{t('secretVariable')}<input value={input.secret_ref.replace(/^env:/, '')} onChange={(event) => setInput({ ...input, secret_ref: `env:${event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '')}` })} placeholder="N8N_API_KEY" required /></label>{input.kind === 'n8n' && <label>{t('n8nVersion')}<select value={input.n8n_minor ?? '2.32'} onChange={(event) => setInput({ ...input, n8n_minor: event.target.value as RuntimeConnectionInput['n8n_minor'] })}><option>2.32</option><option>2.31</option><option>2.30</option></select></label>}</div><p className="runtime-form__hint">{t('secretVariableHint')}</p><div className="modal__actions">{editingId && <button type="button" className="button button--secondary" onClick={resetForm}>{t('cancel')}</button>}<button className="button button--primary" disabled={busyId === 'form'}>{busyId === 'form' ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}{editingId ? t('saveChanges') : t('addConnection')}</button></div></form> : <div className="notice">{t('connectionOwnerOnly')}</div>}
  </div></div>
}

function ArchiveImportModal({ workspaceId, busy, setBusy, onClose, onRestored }: { workspaceId: string; busy: boolean; setBusy: (value: boolean) => void; onClose: () => void; onRestored: (project: Project) => void }) {
  const { t } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [validation, setValidation] = useState<ProjectArchiveValidation | null>(null)
  const [error, setError] = useState('')
  async function inspect(nextFile: File | undefined) {
    if (!nextFile) return
    setFile(nextFile); setValidation(null); setError(''); setBusy(true)
    try { setValidation(await api.validateProjectArchive(nextFile)) }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('invalidBackup')) }
    finally { setBusy(false) }
  }
  async function restore() {
    if (!file || !validation || !workspaceId) return
    setBusy(true); setError('')
    try { onRestored((await api.restoreProjectArchive(workspaceId, file)).project) }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : t('error')) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal modal--small"><div className="modal__header"><div><span className="section-label">APA · BACKUP</span><h2>{t('restoreBackup')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{t('restoreBackupHint')}</p><label className="file-drop"><FileArchive size={24} /><strong>{file?.name || t('chooseBackup')}</strong><input type="file" accept=".zip,.apa.zip,application/zip" onChange={(event) => void inspect(event.target.files?.[0])} /></label>{busy && <div className="loading-state"><LoaderCircle className="spin" size={18} />{t('checkingBackup')}</div>}{error && <div className="notice notice--error">{error}</div>}{validation && <div className="archive-validation"><strong>{validation.project_name}</strong><span>{t('backupRevisions')}: {validation.counts.revisions}</span><span>{t('backupInterviews')}: {validation.counts.sessions}</span><span>{t('backupMessages')}: {validation.counts.messages}</span><small>{t('backupCredentialsWarning')}</small></div>}<div className="modal__actions"><button className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={!validation || busy} onClick={() => void restore()}><ArchiveRestore size={16} />{t('restore')}</button></div></div></div>
}

function N8nImportModal({ busy, onClose, onImport }: { busy: boolean; onClose: () => void; onImport: (workflow: Record<string, unknown>, minor: '2.32' | '2.31' | '2.30') => Promise<void> }) {
  const { t } = useI18n()
  const [workflow, setWorkflow] = useState<Record<string, unknown> | null>(null)
  const [fileName, setFileName] = useState('')
  const [minor, setMinor] = useState<'2.32' | '2.31' | '2.30'>('2.32')
  const [parseError, setParseError] = useState('')
  const nodes = Array.isArray(workflow?.nodes) ? workflow.nodes : []
  async function readFile(file: File | undefined) {
    if (!file) return
    setParseError(''); setFileName(file.name)
    try {
      const parsed: unknown = JSON.parse(await file.text())
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error()
      const value = parsed as Record<string, unknown>
      setWorkflow(value)
      const detected = (value.meta as Record<string, unknown> | undefined)?.targetN8nMinor
      if (detected === '2.32' || detected === '2.31' || detected === '2.30') setMinor(detected)
    } catch { setWorkflow(null); setParseError(t('invalidJsonFile')) }
  }
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><form className="modal modal--small n8n-import-modal" onSubmit={(event) => { event.preventDefault(); if (workflow) void onImport(workflow, minor) }}><div className="modal__header"><div><span className="section-label">N8N · AS-IS</span><h2>{t('importN8n')}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{t('importN8nHint')}</p><label className="file-drop"><FileJson size={24} /><strong>{fileName || t('chooseN8nJson')}</strong><input type="file" accept="application/json,.json" onChange={(event) => void readFile(event.target.files?.[0])} /></label>{parseError && <div className="notice notice--error">{parseError}</div>}<label className="n8n-import-version">{t('n8nVersion')}<select value={minor} onChange={(event) => setMinor(event.target.value as typeof minor)}><option>2.32</option><option>2.31</option><option>2.30</option></select></label>{workflow && <div className="n8n-import-summary"><strong>{String(workflow.name || t('unnamedWorkflow'))}</strong><span>{t('workflowNodes')}: {nodes.length}</span><span>{t('importAsIs')}</span></div>}<div className="modal__actions"><button type="button" className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={!workflow || busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}{t('import')}</button></div></form></div>
}

function TemplateCreateModal({ templates, rubric, collections, collectionItems, loading, selectedId, search, name, busy, onName, onSearch, onSelect, onCreateCollection, onToggleCollection, onClose, onSubmit }: {
  templates: ProcessTemplate[]; rubric: Rubric | null; collections: TemplateCollection[]; collectionItems: TemplateCollectionItem[]; loading: boolean; selectedId: string; search: string; name: string; busy: boolean;
  onName: (value: string) => void; onSearch: (value: string) => void;
  onSelect: (template: ProcessTemplate | null) => void; onCreateCollection: (name: string) => Promise<void>; onToggleCollection: (template: ProcessTemplate, collectionId: string, included: boolean) => Promise<void>; onClose: () => void; onSubmit: (event: FormEvent) => void
}) {
  const { t } = useI18n()
  const selected = templates.find((item) => item.id === selectedId) ?? null
  const categories = Array.from(new Map(templates.map((item) => [item.category, item.category_name])).entries())
  const firstCategoryId = categories[0]?.[0]
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set(categories[0] ? [categories[0][0]] : []))
  const [rubricFilters, setRubricFilters] = useState<Record<string, string>>({})
  const [collectionFilter, setCollectionFilter] = useState('all')
  const [newCollectionName, setNewCollectionName] = useState('')
  const [showNewCollection, setShowNewCollection] = useState(false)
  const filterDimensions = rubric?.dimensions.filter((dimension) => ['domain', 'automation_mode', 'business_role', 'risk'].includes(dimension.id)) ?? []
  const rubricNames = new Map(rubric?.dimensions.flatMap((dimension) => dimension.entries.map((entry) => [entry.id, entry.name] as const)) ?? [])
  const selectedRubricIds = Object.values(rubricFilters).filter(Boolean)
  const normalizedSearch = search.trim().toLocaleLowerCase()
  const filtered = templates.filter((item) => {
    if (collectionFilter === 'personal' && item.source !== 'user') return false
    if (!['all', 'personal'].includes(collectionFilter) && !collectionItems.some((entry) => entry.collection_id === collectionFilter && entry.template_source === item.source && entry.template_id === item.id)) return false
    if (!selectedRubricIds.every((id) => item.rubric_entry_ids.includes(id))) return false
    const rubricTerms = item.rubric_entry_ids.map((id) => rubricNames.get(id) ?? '').join(' ')
    return !normalizedSearch || `${item.name} ${item.description} ${item.search_terms.join(' ')} ${rubricTerms}`.toLocaleLowerCase().includes(normalizedSearch)
  })
  const groupedTemplates = categories.map(([id, label]) => ({
    id,
    label,
    templates: filtered.filter((template) => template.category === id),
  })).filter((group) => group.templates.length > 0)

  useEffect(() => {
    if (!loading && firstCategoryId) {
      setExpandedCategories((current) => current.size ? current : new Set([firstCategoryId]))
    }
  }, [firstCategoryId, loading])

  function toggleCategory(categoryId: string) {
    setExpandedCategories((current) => {
      const next = new Set(current)
      if (next.has(categoryId)) next.delete(categoryId)
      else next.add(categoryId)
      return next
    })
  }

  function renderTemplate(template: ProcessTemplate) {
    const favorites = collections.find((item) => item.is_favorites)
    const isFavorite = Boolean(favorites && collectionItems.some((item) => item.collection_id === favorites.id && item.template_source === template.source && item.template_id === template.id))
    return <div className={`template-list__item ${selectedId === template.id ? 'is-active' : ''}`} key={`${template.source}-${template.id}`} data-template-id={template.id}><button type="button" className="template-list__main" onClick={() => onSelect(template)}><span className="template-list__icon">{template.agent_enabled ? <Bot size={17} /> : <Workflow size={17} />}</span><span><strong>{template.library_number ? `#${String(template.library_number).padStart(3, '0')} · ` : ''}{template.name}</strong><small>{template.source === 'user' ? t('personalTemplate') : template.status === 'ready' ? t('templateReady') : template.agent_enabled ? t('templateAgentDraft') : t('templateInterviewDraft')}</small></span></button>{favorites && <button type="button" className={`template-favorite ${isFavorite ? 'is-active' : ''}`} aria-label={isFavorite ? t('removeFavorite') : t('addFavorite')} onClick={() => void onToggleCollection(template, favorites.id, isFavorite)}><Star size={15} fill={isFavorite ? 'currentColor' : 'none'} /></button>}</div>
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <form className="modal modal--template-library" onSubmit={onSubmit}>
      <div className="modal__header"><div><span className="section-label">Process IR</span><h2>{t('templateLibrary')}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div>
      <div className="template-toolbar">
        <label className="search-field"><Search size={16} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder={t('templateSearch')} /></label>
        <div className="template-collections-toolbar"><select aria-label={t('templateCollection')} value={collectionFilter} onChange={(event) => setCollectionFilter(event.target.value)}><option value="all">{t('allTemplates')}</option><option value="personal">{t('myTemplates')}</option>{collections.map((collection) => <option value={collection.id} key={collection.id}>{collection.is_favorites ? `★ ${t('favorites')}` : collection.name} ({collection.item_count})</option>)}</select><button type="button" className="icon-button" onClick={() => setShowNewCollection((value) => !value)} aria-label={t('newCollection')} title={t('newCollection')}><FolderPlus size={16} /></button></div>
        {showNewCollection && <div className="template-new-collection"><input value={newCollectionName} onChange={(event) => setNewCollectionName(event.target.value)} placeholder={t('collectionName')} maxLength={160} /><button type="button" className="button button--secondary button--small" disabled={!newCollectionName.trim()} onClick={async () => { await onCreateCollection(newCollectionName.trim()); setNewCollectionName(''); setShowNewCollection(false) }}>{t('create')}</button></div>}
        <div className="template-filters" aria-label={t('templateFilters')}>
          {filterDimensions.map((dimension) => <label key={dimension.id}><span>{dimension.name}</span><select aria-label={dimension.name} value={rubricFilters[dimension.id] ?? ''} onChange={(event) => setRubricFilters((current) => ({ ...current, [dimension.id]: event.target.value }))}><option value="">{t('allValues')}</option>{dimension.entries.filter((entry) => !entry.deprecated).map((entry) => <option value={entry.id} key={entry.id}>{entry.name}</option>)}</select></label>)}
          {selectedRubricIds.length > 0 && <button type="button" className="icon-button template-filters__reset" onClick={() => setRubricFilters({})} aria-label={t('resetFilters')} title={t('resetFilters')}><RotateCcw size={16} /></button>}
        </div>
      </div>
      <div className="template-library">
        <div className="template-list" data-testid="template-list">
          <button type="button" className={`template-list__item ${selectedId === 'blank' ? 'is-active' : ''}`} onClick={() => onSelect(null)} data-testid="template-blank"><span className="template-list__icon"><Plus size={17} /></span><span><strong>{t('blankProcess')}</strong><small>Process IR</small></span></button>
          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={18} />{t('loading')}</div> : groupedTemplates.length === 0 ? <div className="template-list__empty">{t('noMatchingTemplates')}</div> : groupedTemplates.map((group) => {
            const expanded = Boolean(normalizedSearch) || selectedRubricIds.length > 0 || expandedCategories.has(group.id)
            const ready = group.templates.filter((template) => template.status === 'ready')
            const drafts = group.templates.filter((template) => template.status === 'interview_draft')
            return <section className="template-tree-group" key={group.id}>
              <button type="button" className="template-tree-group__header" onClick={() => toggleCategory(group.id)} aria-expanded={expanded} data-template-category={group.id}><span>{expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}{group.label}</span><small>{group.templates.length}</small></button>
              {expanded && <div className="template-tree-group__content">
                {ready.length > 0 && <div className="template-tree-subgroup"><div className="template-tree-subgroup__label"><span>{t('templateGroupReady')}</span><small>{ready.length}</small></div>{ready.map(renderTemplate)}</div>}
                {drafts.length > 0 && <div className="template-tree-subgroup"><div className="template-tree-subgroup__label"><span>{t('templateGroupInterview')}</span><small>{drafts.length}</small></div>{drafts.map(renderTemplate)}</div>}
              </div>}
            </section>
          })}
        </div>
        <div className="template-preview" data-testid="template-preview">
          {selected ? <><div className="template-preview__labels"><span className="template-preview__category">{selected.category_name}</span><span className={`template-status template-status--${selected.status}`}>{selected.source === 'user' ? t('personalTemplate') : selected.status === 'ready' ? t('templateReady') : selected.agent_enabled ? t('templateAgentDraft') : t('templateInterviewDraft')}</span>{selected.priority && <span className="template-priority">{selected.priority}</span>}{selected.library_number && <span className="template-priority">#{String(selected.library_number).padStart(3, '0')}</span>}</div><h3>{selected.name}</h3><p>{selected.description}</p><div className="template-preview__rubrics">{filterDimensions.map((dimension) => selected.rubric_entry_ids.map((id) => dimension.entries.find((entry) => entry.id === id)).find(Boolean)).filter(Boolean).map((entry) => <span key={entry!.id}>{entry!.name}</span>)}</div><div className="template-preview__collections"><strong>{t('templateCollections')}</strong>{collections.map((collection) => { const included = collectionItems.some((item) => item.collection_id === collection.id && item.template_source === selected.source && item.template_id === selected.id); return <label key={collection.id}><input type="checkbox" checked={included} onChange={() => void onToggleCollection(selected, collection.id, included)} />{collection.is_favorites ? t('favorites') : collection.name}</label> })}</div><div className="template-preview__metrics"><span><Workflow size={15} />{selected.step_count}</span><span><Users size={15} />{selected.actor_count}</span><span><MonitorCog size={15} />{selected.system_count}</span>{selected.agent_enabled && <span><Bot size={15} />{t('agentReadyMode')}</span>}{selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer">{t('templateSource')}{selected.source_template_id ? ` #${selected.source_template_id}` : ''}</a>}</div><div className="template-preview__steps"><strong>{t('templatePreview')}</strong>{selected.preview_steps.map((step, index) => <div key={`${step}-${index}`}><i>{index + 1}</i><span>{step}</span></div>)}</div></> : <><span className="template-preview__empty"><Bot size={24} /></span><h3>{t('blankProcess')}</h3><p>{t('interviewHint')}</p></>}
        </div>
      </div>
      <label className="template-project-name">{t('projectName')}<input value={name} onChange={(event) => onName(event.target.value)} required maxLength={200} /></label>
      <div className="modal__actions"><button type="button" className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Plus size={17} />}{t('create')}</button></div>
    </form>
  </div>
}
