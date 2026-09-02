import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  Activity, AlertCircle, ArrowDown, ArrowLeft, ArrowUp, Bot, Check, ChevronRight, Clock3, Code2, Download, FileClock, FileText, GitBranch, History, LayoutTemplate,
  Archive, FileUp, LoaderCircle, MessageSquareText, PanelRight, RotateCcw, Save, Send, ShieldCheck, SlidersHorizontal, Sparkles, Undo2,
  Trash2, Workflow, X,
} from 'lucide-react'
import { api, ApiError, downloadExport, downloadProjectArchive, type AgentTarget, type AppSpecTarget, type ExportFormat, type OpenClawVersion } from '../api'
import { useI18n } from '../i18n/context'
import { calculateDiagramReadiness } from '../readiness-metrics'
import { readinessReason } from '../readiness-copy'
import type { AgentEvaluationRun, AgentPackageDelivery, AgentPackageDeliveryPreview, AgentPilotGate, AgentReadiness, AgentRun, AnalystSessionDetail, CrossInterviewConflictScan, InterviewDocument, InterviewEvidenceSummary, InterviewProposalResponse, InterviewTemplateMatch, N8nImportResult, N8nPublication, N8nPublicationPreview, ProcessIR, ProcessStep, ProcessTemplateSuggestion, Project, ProposedPatch, PythonCodeValidation, Readiness, Revision, Rubric, RuntimeConnectionProfile, TemplateCollection } from '../types'
import { Brand } from './Brand'
import { LanguageSwitch } from './LanguageSwitch'
import { ProcessCanvas } from './ProcessCanvas'

type PanelTab = 'analyst' | 'properties' | 'custom_code' | 'agent_contract' | 'readiness'
type MobileView = 'canvas' | 'analyst' | 'custom_code' | 'agent_contract' | 'readiness'

function workspaceError(reason: unknown, t: ReturnType<typeof useI18n>['t']) {
  if (reason instanceof ApiError && reason.status === 404) return t('projectUnavailable')
  if (reason instanceof ApiError && ['invalid_llm_patch', 'llm_request_failed'].includes(reason.code ?? '')) return t('modelPatchError')
  if (reason instanceof ApiError && reason.code === 'invalid_process_change') return t('noProcessChange')
  return reason instanceof ApiError ? reason.message : t('error')
}

export function WorkspaceScreen({ projectId, onBack }: { projectId: string; onBack: () => void }) {
  const { locale, t } = useI18n()
  const [project, setProject] = useState<Project | null>(null)
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [agentReadiness, setAgentReadiness] = useState<AgentReadiness | null>(null)
  const [session, setSession] = useState<AnalystSessionDetail | null>(null)
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [rubric, setRubric] = useState<Rubric | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [panelTab, setPanelTab] = useState<PanelTab>('analyst')
  const [mobileView, setMobileView] = useState<MobileView>('analyst')
  const [message, setMessage] = useState('')
  const [messageError, setMessageError] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [showAgentRuns, setShowAgentRuns] = useState(false)
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([])
  const [showPilotGate, setShowPilotGate] = useState(false)
  const [pilotRuntime, setPilotRuntime] = useState<'openclaw' | 'hermes'>('openclaw')
  const [pilotGate, setPilotGate] = useState<AgentPilotGate | null>(null)
  const [evaluations, setEvaluations] = useState<AgentEvaluationRun[]>([])
  const [showExport, setShowExport] = useState(false)
  const [showSaveTemplate, setShowSaveTemplate] = useState(false)
  const [showInterviewImport, setShowInterviewImport] = useState(false)
  const [editingInterview, setEditingInterview] = useState<InterviewDocument | null>(null)
  const [evidenceSegmentId, setEvidenceSegmentId] = useState<string | null>(null)
  const [collections, setCollections] = useState<TemplateCollection[]>([])
  const [exportFormat, setExportFormat] = useState<ExportFormat>('spec')
  const [appSpecTarget, setAppSpecTarget] = useState<AppSpecTarget>('codex')
  const [n8nTarget, setN8nTarget] = useState('2.32')
  const [includeN8nGuide, setIncludeN8nGuide] = useState(true)
  const [agentTarget, setAgentTarget] = useState<AgentTarget>('openclaw')
  const [openclawVersion, setOpenclawVersion] = useState<OpenClawVersion>('2026.8.2')
  const [templateSuggestion, setTemplateSuggestion] = useState<ProcessTemplateSuggestion | null>(null)
  const [templateFeedback, setTemplateFeedback] = useState('')
  const [dismissedTemplateIds, setDismissedTemplateIds] = useState<string[]>([])
  const [importReport, setImportReport] = useState<N8nImportResult | null>(() => {
    const stored = sessionStorage.getItem(`apa_n8n_import_report_${projectId}`)
    return stored ? JSON.parse(stored) as N8nImportResult : null
  })
  const loadedProject = useRef<string | null>(null)

  const load = useCallback(async () => {
    const rubricRequest = api.rubric(locale).catch(() => null)
    const [nextProject, nextReadiness, nextRevisions, sessions, nextRubric] = await Promise.all([
      api.project(projectId), api.readiness(projectId), api.revisions(projectId), api.sessions(projectId), rubricRequest,
    ])
    let activeSession = sessions.find((item) => item.status === 'active')
    if (!activeSession) activeSession = await api.createSession(projectId, locale, nextProject.current_revision.perspective === 'as_is' ? 'as_is_completion' : 'discovery')
    const sessionDetail = await api.session(activeSession.id)
    setProject(nextProject)
    setReadiness(nextReadiness)
    setRevisions(nextRevisions)
    setRubric(nextRubric)
    setSession(sessionDetail)
    setAgentReadiness(nextProject.target_mode === 'agent' ? await api.agentReadiness(projectId) : null)
  }, [locale, projectId])

  useEffect(() => {
    if (loadedProject.current === projectId) return
    loadedProject.current = projectId
    setBusy(true)
    load().catch((reason) => {
      loadedProject.current = null
      setError(workspaceError(reason, t))
    }).finally(() => setBusy(false))
  }, [load, projectId, t])

  useEffect(() => {
    if (importReport) setN8nTarget(importReport.source_minor)
  }, [importReport])

  const selectedStep = useMemo(() => project?.current_revision.process_ir.steps.find((item) => item.id === selectedStepId) ?? null, [project, selectedStepId])
  const seedProject = Boolean(project && project.current_revision.version_number === 1 && project.current_revision.process_ir.steps.length <= 2)
  const diagramReadiness = readiness ? calculateDiagramReadiness(readiness) : 0
  const hasN8nSource = revisions.some((revision) => revision.source === 'import')

  async function refreshSession() {
    if (!session) return
    const [nextProject, nextReadiness, nextRevisions, nextSession] = await Promise.all([
      api.project(projectId), api.readiness(projectId), api.revisions(projectId), api.session(session.id),
    ])
    setProject(nextProject); setReadiness(nextReadiness); setRevisions(nextRevisions); setSession(nextSession)
    setAgentReadiness(nextProject.target_mode === 'agent' ? await api.agentReadiness(projectId) : null)
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    if (!session || !message.trim()) return
    const content = message.trim()
    setMessage('')
    await deliverMessage(content)
  }

  async function deliverMessage(content: string) {
    if (!session) return
    setBusy(true)
    setError('')
    setMessageError('')
    setTemplateFeedback('')
    try {
      const interviewText = [...session.messages.filter((item) => item.role === 'user').map((item) => item.content), content].join('\n')
      const suggestionRequest = session.mode === 'as_is_completion' ? Promise.resolve(null) : api.suggestTemplate(interviewText, locale, dismissedTemplateIds).catch(() => null)
      await api.sendTurn(session.id, content)
      const suggestion = await suggestionRequest
      setTemplateSuggestion(suggestion)
      await refreshSession()
    } catch (reason) {
      const nextError = workspaceError(reason, t)
      const messageWasSaved = reason instanceof ApiError && ['invalid_llm_patch', 'llm_request_failed'].includes(reason.code ?? '')
      if (messageWasSaved) await refreshSession().catch(() => undefined)
      else setMessage(content)
      setMessageError(nextError)
    } finally { setBusy(false) }
  }

  async function applySuggestedTemplate() {
    if (!project || !templateSuggestion) return
    setBusy(true); setError(''); setTemplateFeedback('')
    try {
      const applied = await api.applyTemplate(project.id, templateSuggestion.template.id, project.current_revision_id, locale)
      if (applied.current_revision_id === project.current_revision_id) setTemplateFeedback(t('templateAlreadyApplied'))
      setDismissedTemplateIds((ids) => ids.includes(templateSuggestion.template.id) ? ids : [...ids, templateSuggestion.template.id])
      setTemplateSuggestion(null)
      await refreshSession()
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function retryLastMessage() {
    const lastMessage = session?.messages.at(-1)
    if (!lastMessage || lastMessage.role !== 'user') return
    await deliverMessage(lastMessage.content)
  }

  async function resolveProposal(proposal: ProposedPatch, action: 'accept' | 'reject') {
    if (!project) return
    setBusy(true); setError('')
    try {
      if (action === 'accept') await api.acceptProposal(proposal.id, project.current_revision_id)
      else await api.rejectProposal(proposal.id)
      await refreshSession()
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function undo() {
    if (!project) return
    setBusy(true); setError('')
    try { await api.undo(project.id, project.current_revision_id); await refreshSession() }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function restore(targetId: string) {
    if (!project) return
    setBusy(true); setError('')
    try { await api.restore(project.id, project.current_revision_id, targetId); await refreshSession(); setShowHistory(false) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function saveStep(nextStep: ProcessStep) {
    if (!project) return
    const stepIndex = project.current_revision.process_ir.steps.findIndex((item) => item.id === nextStep.id)
    if (stepIndex < 0) return
    setBusy(true); setError('')
    try {
      await api.patchProject(project.id, project.current_revision_id, [
        { op: 'replace', path: `/steps/${stepIndex}`, value: nextStep },
      ])
      await refreshSession()
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function downloadBackup() {
    if (!project) return
    setBusy(true); setError('')
    try { await downloadProjectArchive(project) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function savePassport(passport: ProcessIR['passport']) {
    if (!project) return
    setBusy(true); setError('')
    try {
      await api.patchProject(project.id, project.current_revision_id, [
        { op: 'replace', path: '/passport', value: passport },
      ])
      await refreshSession()
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function confirmClassification(entryIds: string[]) {
    if (!project || !rubric) return
    setBusy(true); setError('')
    try {
      await api.confirmClassification(project.id, project.current_revision_id, rubric.version, entryIds)
      await refreshSession()
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function setTargetMode(targetMode: 'process' | 'agent') {
    if (!project) return
    if (project.target_mode === targetMode) return
    setBusy(true); setError('')
    try {
      const nextProject = await api.setTargetMode(project.id, targetMode)
      setProject(nextProject)
      setAgentReadiness(targetMode === 'agent' ? await api.agentReadiness(project.id) : null)
      if (targetMode === 'agent') setPanelTab('readiness')
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function saveAsTemplate(name: string, description: string, collectionIds: string[], favorite: boolean) {
    if (!project) return
    setBusy(true); setError('')
    try {
      await api.saveProjectAsTemplate(project.id, name, description, collectionIds, favorite)
      setShowSaveTemplate(false)
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function openSaveTemplate() {
    setBusy(true); setError('')
    try { setCollections(await api.templateCollections()); setShowSaveTemplate(true) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function openAgentRuns() {
    if (!project) return
    setBusy(true); setError('')
    try { setAgentRuns(await api.agentRuns(project.id)); setShowAgentRuns(true) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function resolveAgentIncident(incidentId: string) {
    if (!project) return
    setBusy(true); setError('')
    try { await api.resolveAgentIncident(incidentId); setAgentRuns(await api.agentRuns(project.id)) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function replayAgentIncident(incidentId: string, revision: 'original' | 'current') {
    if (!project) return
    setBusy(true); setError('')
    try { await api.replayAgentIncident(incidentId, revision); setAgentRuns(await api.agentRuns(project.id)) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function loadPilotGate(runtime: 'openclaw' | 'hermes') {
    if (!project) return
    setBusy(true); setError('')
    try {
      const [nextGate, nextEvaluations] = await Promise.all([api.agentPilotGate(project.id, runtime), api.agentEvaluations(project.id)])
      setPilotRuntime(runtime); setPilotGate(nextGate); setEvaluations(nextEvaluations.filter((item) => item.runtime === runtime)); setShowPilotGate(true)
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  async function approvePilotBaseline() {
    if (!project || !pilotGate?.latest_evaluation) return
    setBusy(true); setError('')
    try { await api.approveAgentBaseline(project.id, pilotGate.latest_evaluation.id); await loadPilotGate(pilotRuntime) }
    catch (reason) { setError(workspaceError(reason, t)); setBusy(false) }
  }

  async function dispatchPilot() {
    if (!project || !pilotGate?.pilot_ready) return
    setBusy(true); setError('')
    try {
      await api.dispatchAgent(project.id, pilotRuntime)
      setAgentRuns(await api.agentRuns(project.id))
      setShowPilotGate(false)
      setShowAgentRuns(true)
    } catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }

  if (!project || !readiness || !session) {
    if (error) return <div className="full-loading full-loading--error"><AlertCircle size={24} /><strong>{error}</strong><button className="button button--secondary" onClick={onBack}><ArrowLeft size={16} />{t('back')}</button></div>
    return <div className="full-loading"><LoaderCircle className="spin" size={24} />{t('loading')}</div>
  }

  return (
    <div className={`workspace ${seedProject ? 'workspace--interview-first' : ''}`} data-help-topic="project">
      <header className="workspace-header">
        <div className="workspace-header__identity"><Brand compact /><button className="icon-button" onClick={onBack} title={t('back')}><ArrowLeft size={18} /></button><div className="project-crumb"><span>{t('projects')} /</span><strong>{project.name}</strong></div></div>
        <div className="workspace-header__status"><span className="target-mode-control"><button data-help-topic="process" className={project.target_mode === 'process' ? 'is-active' : ''} disabled={busy} onClick={() => void setTargetMode('process')}>{t('processMode')}</button><button data-help-topic="agent" className={project.target_mode === 'agent' ? 'is-active' : ''} disabled={busy} onClick={() => void setTargetMode('agent')}><Bot size={13} />{t('agentReadyMode')}</button></span><span className={`perspective-pill perspective-pill--${project.current_revision.perspective}`}>{t(project.current_revision.perspective === 'as_is' ? 'asIs' : 'toBe')}</span><span data-help-topic="readiness" className={`readiness-pill readiness-pill--${(project.target_mode === 'agent' ? agentReadiness?.agentReady : diagramReadiness >= 85) ? 'ok' : 'warning'}`} title={project.target_mode === 'agent' ? t('agentReadiness') : t('diagramReadiness')}><i>{project.target_mode === 'agent' ? agentReadiness?.overall ?? 0 : diagramReadiness}%</i><span>{project.target_mode === 'agent' ? t('agentReadiness') : t('diagramReadiness')}</span></span><span className="revision-pill">v{project.current_revision.version_number}</span></div>
        <div className="workspace-header__actions"><LanguageSwitch /><button className="icon-button" onClick={undo} disabled={!project.current_revision.inverse_patch || busy} title={t('undo')}><Undo2 size={18} /></button><button className="icon-button" onClick={() => void openSaveTemplate()} disabled={busy} title={t('saveAsTemplate')} aria-label={t('saveAsTemplate')}><Save size={18} /></button><button className="icon-button" data-help-topic="backup" onClick={() => void downloadBackup()} disabled={busy} title={t('downloadBackup')} aria-label={t('downloadBackup')}><Archive size={18} /></button>{project.target_mode === 'agent' && <><button className="icon-button" data-help-topic="agent" onClick={() => void loadPilotGate(pilotRuntime)} disabled={busy} title={t('pilotGate')} aria-label={t('pilotGate')}><ShieldCheck size={18} /></button><button className="icon-button" data-help-topic="agent" onClick={() => void openAgentRuns()} disabled={busy} title={t('agentRunHistory')} aria-label={t('agentRunHistory')}><Activity size={18} /></button></>}<button className="button button--secondary button--compact" data-help-topic="history" onClick={() => setShowHistory(true)} title={t('history')}><History size={17} /><span>{t('history')}</span></button><button className="button button--primary button--compact" data-help-topic="export" onClick={() => setShowExport(true)} title={t('export')}><Download size={17} /><span>{t('export')}</span></button></div>
      </header>

      <nav className="mobile-workspace-tabs">
        <button className={mobileView === 'canvas' ? 'is-active' : ''} onClick={() => setMobileView('canvas')}><PanelRight size={17} />{t('canvas')}</button>
        <button className={mobileView === 'analyst' ? 'is-active' : ''} onClick={() => { setMobileView('analyst'); setPanelTab('analyst') }}><MessageSquareText size={17} />{t('analyst')}</button>
        <button className={mobileView === 'custom_code' ? 'is-active' : ''} onClick={() => { setMobileView('custom_code'); setPanelTab('custom_code') }}><Code2 size={17} />{t('customCodeMobile')}</button>
        {project.target_mode === 'agent' && <button className={mobileView === 'agent_contract' ? 'is-active' : ''} onClick={() => { setMobileView('agent_contract'); setPanelTab('agent_contract') }}><ShieldCheck size={17} />{t('agentContractMobile')}</button>}
        <button className={mobileView === 'readiness' ? 'is-active' : ''} onClick={() => { setMobileView('readiness'); setPanelTab('readiness') }}><SlidersHorizontal size={17} />{t('readiness')}</button>
      </nav>

      {error && <div className="workspace-error"><span>{error}</span><button onClick={() => setError('')}><X size={16} /></button></div>}
      {importReport && <div className="import-report" data-testid="import-report"><div><strong>{t('importReport')}</strong><span>n8n {importReport.source_minor} · {t('recognizedNodes')}: {importReport.diagnostics.knownNodeCount}/{importReport.diagnostics.nodeCount}</span>{importReport.diagnostics.unknownNodes.length > 0 && <span>{t('unknownNodes')}: {importReport.diagnostics.unknownNodes.map((item) => item.name).join(', ')}</span>}{importReport.diagnostics.credentialReferences.length > 0 && <span>{t('credentialReferences')}: {importReport.diagnostics.credentialReferences.length}</span>}<small>{t('importNeedsInterview')}</small></div><button className="icon-button" onClick={() => { sessionStorage.removeItem(`apa_n8n_import_report_${projectId}`); setImportReport(null) }} aria-label={t('close')}><X size={16} /></button></div>}

      <main className="workspace-main">
        <section className={`canvas-pane mobile-view-${mobileView}`} data-help-topic="diagram">
          <div className="pane-header"><div><span className="section-label">Process IR · v{project.current_revision.version_number}</span><h1>{project.current_revision.process_ir.process.name}</h1></div><span className="maturity-badge">{project.current_revision.process_ir.process.maturity.replace('_', ' ')}</span></div>
          <ProcessCanvas key={mobileView === 'canvas' ? 'canvas-visible' : 'canvas-hidden'} process={project.current_revision.process_ir} selectedId={selectedStepId} onSelect={(id) => { setSelectedStepId(id); setPanelTab('properties') }} />
        </section>

        <aside className={`work-panel mobile-view-${mobileView}`} data-help-topic="analyst">
          <div className="panel-tabs">
            <button className={panelTab === 'analyst' ? 'is-active' : ''} onClick={() => setPanelTab('analyst')}><MessageSquareText size={16} />{t('analyst')}</button>
            <button className={panelTab === 'properties' ? 'is-active' : ''} onClick={() => setPanelTab('properties')}><SlidersHorizontal size={16} />{t('properties')}</button>
            <button className={panelTab === 'custom_code' ? 'is-active' : ''} onClick={() => setPanelTab('custom_code')}><Code2 size={16} />{t('customCode')}</button>
            {project.target_mode === 'agent' && <button className={panelTab === 'agent_contract' ? 'is-active' : ''} onClick={() => setPanelTab('agent_contract')}><ShieldCheck size={16} />{t('agentContract')}</button>}
            <button className={panelTab === 'readiness' ? 'is-active' : ''} onClick={() => setPanelTab('readiness')}><Sparkles size={16} />{t('readiness')}</button>
          </div>
          {panelTab === 'analyst' && <AnalystPanel session={session} project={project} busy={busy} message={message} messageError={messageError} suggestion={templateSuggestion} templateFeedback={templateFeedback} setMessage={(value) => { setMessage(value); setMessageError('') }} onSend={sendMessage} onRetry={retryLastMessage} onResolve={resolveProposal} onUseTemplate={applySuggestedTemplate} onImportInterview={() => setShowInterviewImport(true)} onEditInterview={(document, segmentId = null) => { setEvidenceSegmentId(segmentId); setEditingInterview(document) }} onCombinedProposed={(created) => setSession((current) => current ? { ...current, messages: [...current.messages, created.message], proposed_patches: [...current.proposed_patches, created.proposal] } : current)} onDismissTemplate={() => { if (templateSuggestion) setDismissedTemplateIds((ids) => [...ids, templateSuggestion.template.id]); setTemplateSuggestion(null); setTemplateFeedback('') }} />}
          {panelTab === 'properties' && <PropertiesPanel step={selectedStep} project={project} rubric={rubric} busy={busy} onSave={saveStep} onSavePassport={savePassport} onConfirmClassification={confirmClassification} />}
          {panelTab === 'custom_code' && <CustomCodePanel step={selectedStep} project={project} busy={busy} onSave={saveStep} />}
          {panelTab === 'agent_contract' && <AgentContractPanel project={project} busy={busy} onSave={saveStep} />}
          {panelTab === 'readiness' && (project.target_mode === 'agent' && agentReadiness ? <AgentReadinessPanel readiness={agentReadiness} /> : <ReadinessPanel readiness={readiness} />)}
        </aside>
      </main>

      {showHistory && <HistoryDrawer revisions={revisions} currentId={project.current_revision_id} busy={busy} onRestore={restore} onClose={() => setShowHistory(false)} />}
      {showAgentRuns && <AgentRunsDrawer runs={agentRuns} busy={busy} onResolve={resolveAgentIncident} onReplay={replayAgentIncident} onClose={() => setShowAgentRuns(false)} />}
      {showPilotGate && pilotGate && <PilotGateDrawer gate={pilotGate} evaluations={evaluations} runtime={pilotRuntime} busy={busy} onRuntime={(value) => void loadPilotGate(value)} onApprove={() => void approvePilotBaseline()} onDispatch={() => void dispatchPilot()} onClose={() => setShowPilotGate(false)} />}
      {showExport && <ExportModal project={project} format={exportFormat} setFormat={setExportFormat} appTarget={appSpecTarget} setAppTarget={setAppSpecTarget} n8nTarget={n8nTarget} setN8nTarget={setN8nTarget} includeN8nGuide={includeN8nGuide} setIncludeN8nGuide={setIncludeN8nGuide} agentTarget={agentTarget} setAgentTarget={setAgentTarget} openclawVersion={openclawVersion} setOpenclawVersion={setOpenclawVersion} readiness={readiness} agentReadiness={agentReadiness} roundTrip={hasN8nSource} perspective={project.current_revision.perspective} busy={busy} onClose={() => setShowExport(false)} onDownload={async () => { setBusy(true); try { await downloadExport(project, exportFormat, n8nTarget, appSpecTarget, agentTarget, openclawVersion, includeN8nGuide, hasN8nSource) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }} />}
      {showSaveTemplate && <SaveTemplateModal project={project} collections={collections} busy={busy} onClose={() => setShowSaveTemplate(false)} onSave={saveAsTemplate} />}
      {showInterviewImport && <InterviewImportModal session={session} locale={locale} onClose={() => setShowInterviewImport(false)} onImported={async () => { setSession(await api.session(session.id)); setShowInterviewImport(false) }} />}
      {editingInterview && <InterviewReviewModal source={editingInterview} project={project} rubric={rubric} focusSegmentId={evidenceSegmentId} onClose={() => { setEditingInterview(null); setEvidenceSegmentId(null) }} onDiscuss={(questions) => { setMessage(`${t('discussTranscriptQuestions')}\n\n${questions.map((item) => `- ${item}`).join('\n')}`); setEditingInterview(null); setEvidenceSegmentId(null); setPanelTab('analyst') }} onTemplateSuggested={(suggestion) => { setTemplateSuggestion(suggestion); setEditingInterview(null); setEvidenceSegmentId(null); setPanelTab('analyst') }} onProposed={(created) => { setSession((current) => current ? { ...current, messages: [...current.messages, created.message], proposed_patches: [...current.proposed_patches, created.proposal] } : current); setEditingInterview(null); setEvidenceSegmentId(null); setPanelTab('analyst') }} onChanged={async () => { const refreshed = await api.session(session.id); setSession(refreshed); setEditingInterview(refreshed.interview_documents.find((item) => item.id === editingInterview.id) ?? null) }} />}
    </div>
  )
}

function SaveTemplateModal({ project, collections, busy, onClose, onSave }: { project: Project; collections: TemplateCollection[]; busy: boolean; onClose: () => void; onSave: (name: string, description: string, collectionIds: string[], favorite: boolean) => Promise<void> }) {
  const { t } = useI18n()
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description)
  const [selected, setSelected] = useState<string[]>([])
  const [favorite, setFavorite] = useState(true)
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><form className="modal modal--small save-template-modal" onSubmit={(event) => { event.preventDefault(); void onSave(name.trim(), description.trim(), selected, favorite) }}><div className="modal__header"><div><span className="section-label">Process IR · v{project.current_revision.version_number}</span><h2>{t('saveAsTemplate')}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><label>{t('templateName')}<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} /></label><label>{t('description')}<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} maxLength={5000} /></label><fieldset><legend>{t('templateCollections')}</legend><label><input type="checkbox" checked={favorite} onChange={(event) => setFavorite(event.target.checked)} />{t('favorites')}</label>{collections.filter((item) => !item.is_favorites).map((collection) => <label key={collection.id}><input type="checkbox" checked={selected.includes(collection.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, collection.id] : current.filter((id) => id !== collection.id))} />{collection.name}</label>)}</fieldset><div className="modal__actions"><button type="button" className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={busy || !name.trim()}><Save size={16} />{t('saveTemplate')}</button></div></form></div>
}

function AnalystPanel({ session, project, busy, message, messageError, suggestion, templateFeedback, setMessage, onSend, onRetry, onResolve, onUseTemplate, onImportInterview, onEditInterview, onCombinedProposed, onDismissTemplate }: {
  session: AnalystSessionDetail; project: Project; busy: boolean; message: string; messageError: string; suggestion: ProcessTemplateSuggestion | null; templateFeedback: string; setMessage: (value: string) => void;
  onSend: (event: FormEvent) => void; onRetry: () => void; onResolve: (proposal: ProposedPatch, action: 'accept' | 'reject') => void;
  onUseTemplate: () => void; onImportInterview: () => void; onEditInterview: (document: InterviewDocument, segmentId?: string | null) => void; onCombinedProposed: (created: { message: InterviewProposalResponse['message']; proposal: ProposedPatch }) => void; onDismissTemplate: () => void
}) {
  const { t } = useI18n()
  const scrollContainer = useRef<HTMLDivElement>(null)
  const proposalByMessage = new Map(session.proposed_patches.map((item) => [item.source_message_id, item]))

  useEffect(() => {
    const container = scrollContainer.current
    if (!container) return
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
  }, [busy, session.messages.length, session.proposed_patches.length, templateFeedback])

  return <div className="analyst-panel"><div className="analyst-scroll" ref={scrollContainer}>
    {session.mode === 'as_is_completion' && <div className="as-is-interview-note"><GitBranch size={15} /><div><strong>{t('asIsInterview')}</strong><span>{project.current_revision.perspective === 'as_is' ? t('asIsInterviewHint') : t('toBeInterviewHint')}</span></div></div>}
    <InterviewEvidenceSummaryCard session={session} project={project} disabled={busy} setMessage={setMessage} onOpenEvidence={onEditInterview} onProposed={onCombinedProposed} />
    {session.interview_documents.map((document) => <div className={`interview-source interview-source--${document.status}`} key={document.id ?? document.content_sha256}><button className="interview-source__open" onClick={() => onEditInterview(document)}><FileText size={16} /><div><strong>{document.title}</strong><span>{document.status === 'purged' ? t('transcriptPurged') : t(document.status === 'reviewed' ? 'transcriptReviewed' : 'transcriptDraft').replace('{count}', String(document.segment_count))}</span><small>{document.data_residency} · {document.retention_until ? new Intl.DateTimeFormat(undefined, { dateStyle: 'short' }).format(new Date(document.retention_until)) : t('retentionManual')}</small></div><ChevronRight size={15} /></button>{document.status !== 'purged' && <button className="icon-button interview-source__purge" title={t('deleteTranscriptContent')} aria-label={`${t('deleteTranscriptContent')}: ${document.title}`} onClick={async () => { if (!document.id || !window.confirm(t('deleteTranscriptConfirm'))) return; onEditInterview(await api.deleteInterviewContent(document.id)) }}><Trash2 size={14} /></button>}</div>)}
    {session.messages.length === 0 && <div className="interview-empty"><span className="analyst-avatar"><Bot size={24} /></span><h2>{t('interviewStart')}</h2><p>{t('interviewHint')}</p></div>}
    {session.messages.map((item) => {
      const proposal = proposalByMessage.get(item.id)
      return <div key={item.id} className={`message message--${item.role}`}>
        {item.role === 'assistant' && <span className="message__avatar"><Bot size={15} /></span>}
        <div className="message__content"><p>{item.content}</p><time>{new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(item.created_at))}</time>
          {proposal && <ProposalCard proposal={proposal} currentRevisionId={project.current_revision_id} busy={busy} onResolve={onResolve} />}
        </div>
      </div>
    })}
    {suggestion && <TemplateSuggestionCard suggestion={suggestion} busy={busy} onUse={onUseTemplate} onDismiss={onDismissTemplate} />}
    {templateFeedback && <div className="message message--assistant message--template-feedback"><span className="message__avatar"><Bot size={15} /></span><div className="message__content"><p>{templateFeedback}</p></div></div>}
    {busy && <div className="thinking"><LoaderCircle className="spin" size={16} /><span>{t('loading')}</span></div>}
  </div>
  {messageError && <div className="message-error"><span>{messageError}</span>{session.messages.at(-1)?.role === 'user' && <button type="button" onClick={onRetry} disabled={busy}><RotateCcw size={14} />{t('retry')}</button>}</div>}
  <form className="message-composer" onSubmit={onSend}><button type="button" className="icon-button" disabled={busy} onClick={onImportInterview} title={t('importTranscript')} aria-label={t('importTranscript')}><FileUp size={18} /></button><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={t('messagePlaceholder')} rows={2} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit() } }} /><button className="icon-button icon-button--primary" disabled={busy || !message.trim()} title={t('send')}><Send size={18} /></button></form>
  </div>
}

function InterviewEvidenceSummaryCard({ session, project, disabled, setMessage, onOpenEvidence, onProposed }: { session: AnalystSessionDetail; project: Project; disabled: boolean; setMessage: (value: string) => void; onOpenEvidence: (document: InterviewDocument, segmentId?: string | null) => void; onProposed: (created: { message: InterviewProposalResponse['message']; proposal: ProposedPatch }) => void }) {
  const { t } = useI18n()
  const [summary, setSummary] = useState<InterviewEvidenceSummary | null>(null)
  const [conflicts, setConflicts] = useState<CrossInterviewConflictScan | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const signature = session.interview_documents.map((item) => `${item.id}:${item.status}:${item.latest_analysis?.id ?? ''}:${item.latest_analysis?.stale ?? false}`).join('|')
  useEffect(() => {
    let active = true
    if (session.interview_documents.length < 2) { setSummary(null); return () => { active = false } }
    void Promise.all([api.interviewEvidenceSummary(session.id), api.crossInterviewConflicts(session.id)]).then(([nextSummary, nextConflicts]) => { if (active) { setSummary(nextSummary); setConflicts(nextConflicts) } }).catch(() => { if (active) { setSummary(null); setConflicts(null) } })
    return () => { active = false }
  }, [session.id, session.interview_documents.length, signature])
  if (!summary || summary.source_count < 2) return null
  const questions = summary.contradictions.map((item) => item.question)
  const build = async () => {
    setBusy(true); setError('')
    try { onProposed(await api.draftMultiInterviewProcess(session.id, project.current_revision_id)) }
    catch (reason) { setError(workspaceError(reason, t)) }
    finally { setBusy(false) }
  }
  const refresh = async () => { const [nextSummary, nextConflicts] = await Promise.all([api.interviewEvidenceSummary(session.id), api.crossInterviewConflicts(session.id)]); setSummary(nextSummary); setConflicts(nextConflicts) }
  const scan = async () => { setBusy(true); setError(''); try { await api.scanCrossInterviewConflicts(session.id); await refresh() } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const resolve = async (id: string, action: 'confirm' | 'dismiss') => { setBusy(true); setError(''); try { await api.resolveCrossInterviewConflict(id, action); await refresh() } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const currentConflicts = conflicts?.conflicts.filter((item) => item.status !== 'dismissed') ?? []
  const semanticQuestions = currentConflicts.filter((item) => item.status === 'confirmed').map((item) => item.question)
  const documentById = new Map(session.interview_documents.map((item) => [item.id, item]))
  const evidenceRefs = (documentId: string, segmentIds: string[], title: string) => {
    const document = documentById.get(documentId)
    if (!document) return null
    return <div className="combined-evidence-refs" key={`${documentId}-${segmentIds.join('-')}`}>{segmentIds.map((segmentId) => { const index = document.segments.findIndex((item) => item.id === segmentId); const segment = document.segments[index]; const timestamp = segment?.start_ms === null || segment?.start_ms === undefined ? '' : ` · ${formatTimestamp(segment.start_ms)}`; return <button key={`${documentId}-${segmentId}`} title={t('openEvidence')} onClick={() => onOpenEvidence(document, segmentId)}><FileText size={12} /><span>{title} · #{index + 1} · {segment?.speaker || t('speakerUnknown')}{timestamp}</span></button> })}</div>
  }
  const conflictEvidence = (conflict: CrossInterviewConflictScan['conflicts'][number]) => conflict.fact_references.map((reference) => { const document = session.interview_documents.find((item) => item.latest_analysis?.id === reference.analysis_id); const fact = document?.latest_analysis?.result.confirmed_facts[reference.fact_index]; if (!document || !fact) return null; return <div className="semantic-conflict__fact" key={`${reference.analysis_id}-${reference.fact_index}`}><p>{fact.statement}</p>{evidenceRefs(document.id ?? '', fact.segment_ids, document.title)}</div> })
  return <section className={`interview-evidence-summary ${summary.can_build_draft ? '' : 'is-blocked'}`} data-testid="interview-evidence-summary"><div className="interview-evidence-summary__head"><span><Workflow size={15} /><strong>{t('combinedInterviews')}</strong></span><b>{summary.source_count}</b></div><p>{t('combinedInterviewStats').replace('{facts}', String(summary.unique_fact_count)).replace('{duplicates}', String(summary.duplicate_fact_count))}</p><details className="combined-facts"><summary>{t('showEvidenceFacts').replace('{count}', String(summary.unique_fact_count))}</summary>{summary.facts.map((fact, index) => <article key={`${fact.statement}-${index}`}><strong>{fact.statement}</strong>{fact.sources.map((source) => evidenceRefs(source.document_id, source.segment_ids, source.document_title))}</article>)}</details>{summary.contradictions.length > 0 && <small>{t('combinedInterviewBlocked').replace('{count}', String(summary.contradictions.length))}</small>}{summary.semantic_scan_required && summary.contradictions.length === 0 && <small>{t('semanticScanRequired')}</small>}{currentConflicts.map((conflict) => <article className={`semantic-conflict semantic-conflict--${conflict.status}`} key={conflict.id}><strong>{conflict.summary}</strong><p>{conflict.reason}</p><div className="semantic-conflict__evidence">{conflictEvidence(conflict)}</div><span>{conflict.question}</span>{conflict.status === 'pending' && <div className="semantic-conflict__actions"><button className="button button--secondary button--small" disabled={busy || disabled} onClick={() => void resolve(conflict.id, 'dismiss')}>{t('notAConflict')}</button><button className="button button--primary button--small" disabled={busy || disabled} onClick={() => void resolve(conflict.id, 'confirm')}><Check size={13} />{t('confirmConflict')}</button></div>}{conflict.status === 'confirmed' && <small>{t('conflictConfirmed')}</small>}</article>)}{error && <small>{error}</small>}{summary.contradictions.length > 0 ? <button className="button button--secondary button--small" disabled={disabled || busy} onClick={() => setMessage(`${t('discussTranscriptQuestions')}\n\n${questions.map((item) => `- ${item}`).join('\n')}`)}><MessageSquareText size={14} />{t('resolveContradictions')}</button> : summary.semantic_scan_required ? <button className="button button--primary button--small" disabled={disabled || busy} onClick={() => void scan()}><Sparkles size={14} />{t('checkSemanticConflicts')}</button> : summary.can_build_draft ? <button className="button button--success button--small" disabled={disabled || busy} onClick={() => void build()}><Workflow size={14} />{t('buildCombinedDraft')}</button> : <button className="button button--secondary button--small" disabled={disabled || busy} onClick={() => setMessage(`${t('discussTranscriptQuestions')}\n\n${semanticQuestions.map((item) => `- ${item}`).join('\n')}`)}><MessageSquareText size={14} />{t('resolveContradictions')}</button>}</section>
}

function InterviewImportModal({ session, locale, onClose, onImported }: { session: AnalystSessionDetail; locale: 'ru' | 'en' | 'es'; onClose: () => void; onImported: () => Promise<void> }) {
  const { t } = useI18n()
  const [title, setTitle] = useState(t('interviewTranscript'))
  const [content, setContent] = useState('')
  const [format, setFormat] = useState<InterviewDocument['source_format']>('plain')
  const [sourceUrl, setSourceUrl] = useState('')
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null)
  const [preview, setPreview] = useState<InterviewDocument | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const readFile = async (file: File) => { setResolvedUrl(null); const extension = file.name.split('.').pop()?.toLowerCase(); if (extension === 'docx' || extension === 'odt') { setBusy(true); setError(''); try { const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let offset = 0; offset < bytes.length; offset += 16_384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16_384)); const resolved = await api.resolveInterviewSource(session.id, extension, { filename: file.name, content_base64: btoa(binary) }); setTitle(resolved.title); setFormat(resolved.source_format); setContent(resolved.content) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } } else { setFormat(extension && ['txt', 'md', 'srt', 'vtt'].includes(extension) ? extension as InterviewDocument['source_format'] : 'txt'); setTitle(file.name.replace(/\.[^.]+$/, '')); setContent(await file.text()) } setPreview(null) }
  const readLink = async (sourceType: 'google_docs' | 'yandex_docs') => { setBusy(true); setError(''); try { const resolved = await api.resolveInterviewSource(session.id, sourceType, { url: sourceUrl.trim() }); setTitle(resolved.title); setFormat(resolved.source_format); setContent(resolved.content); setResolvedUrl(sourceUrl.trim()); setPreview(null) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const inspect = async () => { setBusy(true); setError(''); try { setPreview(await api.previewInterview(session.id, title.trim(), format, content, locale, resolvedUrl)) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const save = async () => { setBusy(true); setError(''); try { await api.importInterview(session.id, title.trim(), format, content, locale, resolvedUrl); await onImported() } catch (reason) { setError(workspaceError(reason, t)); setBusy(false) } }
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="modal transcript-modal"><div className="modal__header"><div><span className="section-label">{t('interviewSource')}</span><h2>{t('importTranscript')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{t('importTranscriptHint')}</p><div className="transcript-link-source"><input aria-label={t('documentLink')} value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://docs.google.com/..." /><button className="button button--secondary button--small" disabled={busy || !sourceUrl.trim()} onClick={() => void readLink('google_docs')}>{t('readGoogleDocs')}</button><button className="button button--secondary button--small" disabled={busy || !sourceUrl.trim()} onClick={() => void readLink('yandex_docs')}>{t('readYandexDocs')}</button></div><label>{t('transcriptTitle')}<input value={title} maxLength={200} onChange={(event) => { setTitle(event.target.value); setPreview(null) }} /></label><label className="transcript-file"><FileUp size={17} />{t('chooseTranscript')}<input type="file" accept=".txt,.md,.srt,.vtt,.docx,.odt,text/plain,text/markdown,text/vtt,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.oasis.opendocument.text" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readFile(file) }} /></label><label>{t('transcriptText')}<textarea rows={9} value={content} onChange={(event) => { setContent(event.target.value); setFormat('plain'); setPreview(null) }} placeholder={t('transcriptTextHint')} /></label>{error && <div className="message-error"><span>{error}</span></div>}{preview && <div className="transcript-preview"><strong>{t('transcriptPreview').replace('{count}', String(preview.segment_count))}</strong>{preview.segments.slice(0, 12).map((segment) => <div key={segment.ordinal}><span>{segment.speaker || t('speakerUnknown')}</span><p>{segment.text}</p></div>)}{preview.segment_count > 12 && <small>{t('transcriptMore').replace('{count}', String(preview.segment_count - 12))}</small>}</div>}<div className="modal__actions"><button className="button button--secondary" onClick={onClose}>{t('cancel')}</button>{!preview ? <button className="button button--primary" disabled={busy || !title.trim() || !content.trim()} onClick={() => void inspect()}>{t('preview')}</button> : <button className="button button--primary" disabled={busy} onClick={() => void save()}><Check size={16} />{t('saveTranscript')}</button>}</div></section></div>
}

function InterviewReviewModal({ source, project, rubric, focusSegmentId, onClose, onChanged, onDiscuss, onProposed, onTemplateSuggested }: { source: InterviewDocument; project: Project; rubric: Rubric | null; focusSegmentId: string | null; onClose: () => void; onChanged: () => Promise<void>; onDiscuss: (questions: string[]) => void; onProposed: (result: InterviewProposalResponse) => void; onTemplateSuggested: (suggestion: ProcessTemplateSuggestion) => void }) {
  const { locale, t } = useI18n()
  const [draft, setDraft] = useState<InterviewDocument>(structuredClone(source))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [templateMatch, setTemplateMatch] = useState<InterviewTemplateMatch | null>(null)
  useEffect(() => setDraft(structuredClone(source)), [source])
  useEffect(() => {
    const analysis = source.latest_analysis
    if (!analysis || analysis.stale) { setTemplateMatch(null); return }
    let active = true
    setTemplateMatch(null)
    api.matchInterviewTemplate(analysis.id, locale)
      .then((result) => { if (active) setTemplateMatch(result) })
      .catch((reason) => { if (active) setError(workspaceError(reason, t)) })
    return () => { active = false }
  }, [locale, source.latest_analysis, t])
  useEffect(() => { if (!focusSegmentId) return; const timer = window.setTimeout(() => window.document.getElementById(`segment-${focusSegmentId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0); return () => window.clearTimeout(timer) }, [focusSegmentId])
  const changed = JSON.stringify({ title: draft.title, language: draft.language, segments: draft.segments }) !== JSON.stringify({ title: source.title, language: source.language, segments: source.segments })
  const updateSegment = (index: number, values: Partial<InterviewDocument['segments'][number]>) => setDraft((current) => ({ ...current, segments: current.segments.map((item, itemIndex) => itemIndex === index ? { ...item, ...values } : item) }))
  const moveSegment = (index: number, direction: -1 | 1) => setDraft((current) => { const segments = [...current.segments]; const target = index + direction; if (target < 0 || target >= segments.length) return current; [segments[index], segments[target]] = [segments[target], segments[index]]; return { ...current, segments } })
  const save = async () => { setBusy(true); setError(''); try { await api.updateInterview(draft); await onChanged() } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const review = async () => { setBusy(true); setError(''); try { const saved = changed ? await api.updateInterview(draft) : source; if (!saved.id) return; await api.reviewInterview(saved.id, saved.segments_sha256); await onChanged(); onClose() } catch (reason) { setError(workspaceError(reason, t)); setBusy(false) } }
  const analyze = async () => { if (!source.id) return; setBusy(true); setError(''); try { await api.analyzeInterview(source.id); await onChanged() } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const propose = async (indices: number[]) => { const analysis = source.latest_analysis; if (!analysis) return; setBusy(true); setError(''); try { onProposed(await api.proposeInterviewFacts(analysis.id, project.current_revision_id, indices)) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const draftProcess = async () => { const analysis = source.latest_analysis; if (!analysis) return; setBusy(true); setError(''); try { onProposed(await api.draftInterviewProcess(analysis.id, project.current_revision_id)) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  const matchTemplate = async () => { const analysis = source.latest_analysis; if (!analysis) return; setBusy(true); setError(''); try { setTemplateMatch(await api.matchInterviewTemplate(analysis.id, locale)) } catch (reason) { setError(workspaceError(reason, t)) } finally { setBusy(false) } }
  if (source.status === 'purged') return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="modal modal--small transcript-purged-modal"><div className="modal__header"><div><span className="section-label">{t('transcriptPurged')}</span><h2>{source.title}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><div className="transcript-purged-notice"><Trash2 size={20} /><div><strong>{t('transcriptContentDeleted')}</strong><p>{t(source.purge_reason === 'retention' ? 'transcriptPurgedRetention' : 'transcriptPurgedManual')}</p></div></div><dl className="transcript-policy"><div><dt>{t('dataResidency')}</dt><dd>{source.data_residency}</dd></div><div><dt>{t('deletedAt')}</dt><dd>{source.purged_at ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(source.purged_at)) : '—'}</dd></div><div><dt>SHA-256</dt><dd>{source.segments_sha256.slice(0, 12)}…</dd></div></dl><div className="modal__actions"><button className="button button--primary" onClick={onClose}>{t('close')}</button></div></section></div>
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="modal transcript-review-modal"><div className="modal__header"><div><span className="section-label">{t(source.status === 'reviewed' ? 'transcriptStatusReviewed' : 'transcriptStatusDraft')}</span><h2>{t('reviewTranscript')}</h2></div><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></div><p className="modal__description">{t('reviewTranscriptHint')}</p><div className="transcript-review-meta"><label>{t('transcriptTitle')}<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label>{t('transcriptLanguage')}<select value={draft.language.split('-')[0]} onChange={(event) => setDraft({ ...draft, language: event.target.value })}><option value="ru">Русский</option><option value="en">English</option><option value="es">Español</option></select></label></div><div className="transcript-segments">{draft.segments.map((segment, index) => <div className={`transcript-segment ${focusSegmentId === segment.id ? 'is-evidence-focus' : ''}`} id={`segment-${segment.id}`} data-evidence-focus={focusSegmentId === segment.id || undefined} key={segment.id ?? `new-${index}`}><div className="transcript-segment__order"><span>{index + 1}</span><button className="icon-button" disabled={index === 0} onClick={() => moveSegment(index, -1)} aria-label={t('moveUp')}><ArrowUp size={14} /></button><button className="icon-button" disabled={index === draft.segments.length - 1} onClick={() => moveSegment(index, 1)} aria-label={t('moveDown')}><ArrowDown size={14} /></button></div><div className="transcript-segment__fields"><input aria-label={`${t('speaker')} ${index + 1}`} placeholder={t('speakerUnknown')} value={segment.speaker ?? ''} onChange={(event) => updateSegment(index, { speaker: event.target.value || null })} /><textarea aria-label={`${t('replica')} ${index + 1}`} rows={2} value={segment.text} onChange={(event) => updateSegment(index, { text: event.target.value })} />{segment.start_ms !== null && <small>{formatTimestamp(segment.start_ms)} – {formatTimestamp(segment.end_ms)}</small>}</div><button className="icon-button transcript-segment__delete" disabled={draft.segments.length === 1} onClick={() => setDraft({ ...draft, segments: draft.segments.filter((_, itemIndex) => itemIndex !== index) })} aria-label={t('deleteReplica')}><Trash2 size={15} /></button></div>)}</div><button className="button button--secondary transcript-add" onClick={() => setDraft({ ...draft, segments: [...draft.segments, { id: null, ordinal: draft.segments.length + 1, speaker: null, text: '', start_ms: null, end_ms: null }] })}>{t('addReplica')}</button>{source.latest_analysis && <InterviewAnalysisView document={source} busy={busy} templateMatch={templateMatch} rubric={rubric} onDiscuss={onDiscuss} onPropose={propose} onDraftProcess={draftProcess} onMatchTemplate={matchTemplate} onUseTemplate={() => templateMatch?.suggestion && onTemplateSuggested(templateMatch.suggestion)} />}{error && <div className="message-error"><span>{error}</span></div>}<div className="modal__actions"><button className="button button--secondary" onClick={onClose}>{t('cancel')}</button>{source.status === 'reviewed' && !changed && (!source.latest_analysis || source.latest_analysis.stale) && <button className="button button--primary" disabled={busy} onClick={() => void analyze()}><Sparkles size={16} />{t(source.latest_analysis ? 'reanalyzeTranscript' : 'analyzeTranscript')}</button>}<button className="button button--secondary" disabled={busy || !changed || !validSegments(draft)} onClick={() => void save()}><Save size={16} />{t('saveDraft')}</button><button className="button button--success" disabled={busy || !validSegments(draft)} onClick={() => void review()}><Check size={16} />{t('confirmTranscript')}</button></div></section></div>
}

function InterviewAnalysisView({
  document: interview,
  busy,
  templateMatch,
  rubric,
  onDiscuss,
  onPropose,
  onDraftProcess,
  onMatchTemplate,
  onUseTemplate,
}: {
  document: InterviewDocument;
  busy: boolean;
  templateMatch: InterviewTemplateMatch | null;
  rubric: Rubric | null;
  onDiscuss: (questions: string[]) => void;
  onPropose: (indices: number[]) => void;
  onDraftProcess: () => void;
  onMatchTemplate: () => void;
  onUseTemplate: () => void;
}) {
  const { t } = useI18n();
  const analysis = interview.latest_analysis;
  const [selected, setSelected] = useState<number[]>([]);
  useEffect(() => setSelected([]), [analysis?.id]);
  if (!analysis) return null;
  const segmentMap = new Map(
    interview.segments.map((item, index) => [
      item.id,
      { ...item, number: index + 1 },
    ]),
  );
  const refs = (ids: string[]) => (
    <div className="evidence-refs">
      {ids.map((id) => {
        const segment = segmentMap.get(id);
        return (
          <button
            key={id}
            onClick={() =>
              window.document
                .getElementById(`segment-${id}`)
                ?.scrollIntoView({ behavior: "smooth", block: "center" })
            }
          >
            #{segment?.number ?? "?"} ·{" "}
            {segment?.speaker || t("speakerUnknown")}
          </button>
        );
      })}
    </div>
  );
  const groups = [
    {
      key: "analysisCandidates",
      items: analysis.result.candidate_facts,
      text: (item: (typeof analysis.result.candidate_facts)[number]) =>
        `${item.statement} — ${item.reason}`,
    },
    {
      key: "analysisContradictions",
      items: analysis.result.contradictions,
      text: (item: (typeof analysis.result.contradictions)[number]) =>
        `${item.summary} ${item.question}`,
    },
    {
      key: "analysisQuestions",
      items: analysis.result.clarification_questions,
      text: (item: (typeof analysis.result.clarification_questions)[number]) =>
        item.question,
    },
  ];
  const rubricNames = new Map(
    rubric?.dimensions.flatMap((dimension) =>
      dimension.entries.map((entry) => [entry.id, entry.name] as const),
    ) ?? [],
  );
  return (
    <section
      className={`interview-analysis ${analysis.stale ? "is-stale" : ""}`}
    >
      <div className="interview-analysis__heading">
        <div>
          <Sparkles size={16} />
          <strong>{t("transcriptAnalysis")}</strong>
        </div>
        {analysis.stale && <span>{t("analysisStale")}</span>}
      </div>
      <div className="analysis-group analysis-group--confirmed">
        <h3>
          {t("analysisConfirmed")}{" "}
          <span>{analysis.result.confirmed_facts.length}</span>
        </h3>
        {analysis.result.confirmed_facts.length ? (
          analysis.result.confirmed_facts.map((item, index) => (
            <article key={index}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(index)}
                  disabled={analysis.stale || busy}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, index]
                        : current.filter((value) => value !== index),
                    )
                  }
                />
                <span>{item.statement}</span>
              </label>
              {refs(item.segment_ids)}
            </article>
          ))
        ) : (
          <small>{t("analysisNone")}</small>
        )}
        {!analysis.stale && analysis.result.confirmed_facts.length > 0 && (
          <>
            <div className="analysis-draft-action">
              <div>
                <strong>{t("buildProcessDraft")}</strong>
                <small>{t("buildProcessDraftHint")}</small>
              </div>
              <button
                className="button button--success button--small"
                disabled={busy}
                onClick={onDraftProcess}
              >
                <Workflow size={14} />
                {t("buildDraft")}
              </button>
            </div>
            <div className="analysis-proposal-actions">
              <small>{t("selectFactsForProposal")}</small>
              <button
                className="button button--primary button--small"
                disabled={busy || selected.length === 0}
                onClick={() => onPropose(selected)}
              >
                <Sparkles size={14} />
                {t("prepareInterviewProposal")}
              </button>
            </div>
          </>
        )}
      </div>
      {!analysis.stale && (
        <div className="analysis-template-match">
          <div className="analysis-template-match__heading">
            <div>
              <LayoutTemplate size={15} />
              <strong>{t("interviewTemplateMatch")}</strong>
            </div>
            <button
              className="button button--secondary button--small"
              disabled={busy || analysis.result.confirmed_facts.length === 0}
              onClick={onMatchTemplate}
            >
              {t(templateMatch ? "matchTemplateAgain" : "matchTemplate")}
            </button>
          </div>
          {templateMatch &&
            (templateMatch.suggestion ? (
              <div className="analysis-template-result">
                <div>
                  <strong>{templateMatch.suggestion.template.name}</strong>
                  <span>
                    {Math.round(templateMatch.suggestion.confidence * 100)}%
                  </span>
                </div>
                <p>{templateMatch.suggestion.reason}</p>
                <div>
                  {templateMatch.proposed_rubric_entry_ids
                    .map((id) => rubricNames.get(id))
                    .filter(Boolean)
                    .slice(0, 5)
                    .map((name) => (
                      <span key={name}>{name}</span>
                    ))}
                </div>
                <button
                  className="button button--primary button--small"
                  onClick={onUseTemplate}
                >
                  <LayoutTemplate size={14} />
                  {t("showTemplateProposal")}
                </button>
              </div>
            ) : (
              <p className="analysis-template-empty">
                {t("noInterviewTemplateMatch")}
              </p>
            ))}
        </div>
      )}
      {groups.map((group) => (
        <div className="analysis-group" key={group.key}>
          <h3>
            {t(group.key as Parameters<typeof t>[0])}{" "}
            <span>{group.items.length}</span>
          </h3>
          {group.items.length ? (
            group.items.map((item, index) => (
              <article key={index}>
                <p>{group.text(item as never)}</p>
                {refs(item.segment_ids)}
              </article>
            ))
          ) : (
            <small>{t("analysisNone")}</small>
          )}
        </div>
      ))}
      {analysis.result.clarification_questions.length > 0 &&
        !analysis.stale && (
          <button
            className="button button--secondary"
            onClick={() =>
              onDiscuss(
                analysis.result.clarification_questions.map(
                  (item) => item.question,
                ),
              )
            }
          >
            <MessageSquareText size={15} />
            {t("discussQuestions")}
          </button>
        )}
    </section>
  );
}

function validSegments(document: InterviewDocument) { return Boolean(document.title.trim()) && document.segments.length > 0 && document.segments.every((item) => item.text.trim()) }
function formatTimestamp(value: number | null) { if (value === null) return ''; const totalSeconds = Math.floor(value / 1000); return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}.${String(value % 1000).padStart(3, '0')}` }

function TemplateSuggestionCard({ suggestion, busy, onUse, onDismiss }: { suggestion: ProcessTemplateSuggestion; busy: boolean; onUse: () => void; onDismiss: () => void }) {
  const { t } = useI18n()
  return <div className="template-suggestion" data-testid="template-suggestion"><div className="template-suggestion__heading"><span><LayoutTemplate size={16} />{t('templateSuggested')}</span><small>{Math.round(suggestion.confidence * 100)}%</small></div><h3>{suggestion.template.name}</h3><p>{suggestion.reason}</p><div className="template-suggestion__steps">{suggestion.template.preview_steps.slice(0, 3).map((step) => <span key={step}>{step}</span>)}</div><div className="template-suggestion__actions"><button className="button button--secondary button--small" disabled={busy} onClick={onDismiss}>{t('dismiss')}</button><button className="button button--primary button--small" disabled={busy} onClick={onUse}><LayoutTemplate size={14} />{t('useTemplate')}</button></div></div>
}

function ProposalCard({ proposal, currentRevisionId, busy, onResolve }: { proposal: ProposedPatch; currentRevisionId: string; busy: boolean; onResolve: (proposal: ProposedPatch, action: 'accept' | 'reject') => void }) {
  const { t } = useI18n()
  return <div className={`proposal proposal--${proposal.status}`}><div className="proposal__heading"><span><Sparkles size={15} />{t('proposal')}</span><small>{proposal.patch.length} ops</small></div><p>{proposal.summary}</p>
    {proposal.draft_quality && <div className="proposal-quality"><strong>{t('draftQuality')}</strong><div><span>{t('evidenceCoverage')}<b>{proposal.draft_quality.evidence_coverage}%</b></span><span>{t('draftSteps')}<b>{proposal.draft_quality.step_count}</b></span><span>{t('draftConnections')}<b>{proposal.draft_quality.edge_count}</b></span><span>{t('draftQuestions')}<b>{proposal.draft_quality.open_question_count}</b></span><span>{t('draftReadiness')}<b>{proposal.draft_quality.readiness}%</b></span></div>{proposal.draft_quality.validation_warning_codes.length > 0 && <small>{t('draftWarnings').replace('{count}', String(proposal.draft_quality.validation_warning_codes.length))}</small>}</div>}
    {proposal.status === 'pending' ? <div className="proposal__actions"><button className="button button--secondary button--small" disabled={busy} onClick={() => onResolve(proposal, 'reject')}><X size={15} />{t('reject')}</button><button className="button button--success button--small" disabled={busy || proposal.base_revision_id !== currentRevisionId} onClick={() => onResolve(proposal, 'accept')}><Check size={15} />{t('accept')}</button></div> : <div className="proposal__resolved">{proposal.status === 'accepted' ? <><Check size={15} />{t('accepted')}</> : <><X size={15} />{t('rejected')}</>}</div>}
  </div>
}

function PropertiesPanel({ step, project, rubric, busy, onSave, onSavePassport, onConfirmClassification }: { step: ProcessStep | null; project: Project; rubric: Rubric | null; busy: boolean; onSave: (step: ProcessStep) => Promise<void>; onSavePassport: (passport: ProcessIR['passport']) => Promise<void>; onConfirmClassification: (entryIds: string[]) => Promise<void> }) {
  const { t } = useI18n()
  const [draft, setDraft] = useState<ProcessStep | null>(step)
  useEffect(() => setDraft(step), [step])
  if (!step) return <PassportEditor project={project} rubric={rubric} busy={busy} onSave={onSavePassport} onConfirmClassification={onConfirmClassification} />
  if (!draft) return null
  const changed = JSON.stringify(draft) !== JSON.stringify(step)
  const toggleData = (field: 'inputs' | 'outputs', id: string) => setDraft((current) => current ? ({ ...current, [field]: current[field].includes(id) ? current[field].filter((item) => item !== id) : [...current[field], id] }) : current)
  return <form className="properties-panel property-form" onSubmit={(event) => { event.preventDefault(); if (changed) void onSave(draft) }}>
    <div className="property-heading"><span className="step-type">{step.type.replace('_', ' ')}</span><h2>{t('editStep')}</h2></div>
    <label><span>{t('name')}</span><input value={draft.title} required onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
    <label><span>{t('description')}</span><textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
    <div className="property-form__grid">
      <label><span>{t('actor')}</span><select value={draft.actorId ?? ''} onChange={(event) => setDraft({ ...draft, actorId: event.target.value || null })}><option value="">—</option>{project.current_revision.process_ir.actors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>{t('system')}</span><select value={draft.systemId ?? ''} onChange={(event) => setDraft({ ...draft, systemId: event.target.value || null })}><option value="">—</option>{project.current_revision.process_ir.systems.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    </div>
    <div className="property-form__grid">
      <label><span>{t('performedBy')}</span><select value={draft.execution.performedBy} onChange={(event) => setDraft({ ...draft, execution: { ...draft.execution, performedBy: event.target.value as ProcessStep['execution']['performedBy'] } })}><option value="human">{t('performedByHuman')}</option><option value="system">{t('performedBySystem')}</option><option value="ai">AI</option></select></label>
      <label><span>{t('autonomy')}</span><select value={draft.execution.autonomy} onChange={(event) => { const autonomy = event.target.value as ProcessStep['execution']['autonomy']; setDraft({ ...draft, execution: { ...draft.execution, autonomy, approvalRequired: autonomy === 'supervised' || draft.execution.approvalRequired } }) }}><option value="manual">{t('autonomyManual')}</option><option value="assist">{t('autonomyAssist')}</option><option value="supervised">{t('autonomySupervised')}</option><option value="autonomous">{t('autonomyAutonomous')}</option></select></label>
    </div>
    <label className="property-form__check"><input type="checkbox" checked={draft.execution.approvalRequired} disabled={draft.execution.autonomy === 'supervised'} onChange={(event) => setDraft({ ...draft, execution: { ...draft.execution, approvalRequired: event.target.checked } })} /><span>{t('approvalRequired')}</span></label>
    <label><span>{t('restrictions')}</span><textarea rows={3} value={draft.execution.restrictions.join('\n')} onChange={(event) => setDraft({ ...draft, execution: { ...draft.execution, restrictions: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) } })} /></label>
    {(['inputs', 'outputs'] as const).map((field) => <fieldset key={field}><legend>{t(field)}</legend><div className="property-form__choices">{project.current_revision.process_ir.dataObjects.length ? project.current_revision.process_ir.dataObjects.map((item) => <label key={item.id}><input type="checkbox" checked={draft[field].includes(item.id)} onChange={() => toggleData(field, item.id)} /><span>{item.name}</span></label>) : <span>—</span>}</div></fieldset>)}
    <div className="property-form__meta"><span>Operation</span><code>{step.operation.kind} / {step.operation.name}</code></div>
    <div className="property-form__meta"><span>{t('missingFields')}</span><div>{step.missingFields.length ? step.missingFields.map((item) => <span className="warning-tag" key={item}>{item}</span>) : <span className="ok-text"><Check size={14} />0</span>}</div></div>
    <button className="button button--primary property-form__save" disabled={busy || !changed || !draft.title.trim()}><Save size={16} />{t('saveChanges')}</button>
  </form>
}

const DEFAULT_PYTHON_SOURCE = `def transform(items):
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    # Apply only confirmed business rules here.
    return items
`

function CustomCodePanel({ step, project, busy, onSave }: { step: ProcessStep | null; project: Project; busy: boolean; onSave: (step: ProcessStep) => Promise<void> }) {
  const { t } = useI18n()
  const [reason, setReason] = useState('')
  const [source, setSource] = useState(DEFAULT_PYTHON_SOURCE)
  const [ruleIds, setRuleIds] = useState<string[]>([])
  const [inputExample, setInputExample] = useState('[]')
  const [outputExample, setOutputExample] = useState('[]')
  const [errorExample, setErrorExample] = useState('[{"json": {}}]')
  const [expectedError, setExpectedError] = useState<'TypeError' | 'ValueError' | 'KeyError'>('ValueError')
  const [errorCases, setErrorCases] = useState('Malformed input is rejected')
  const [inputField, setInputField] = useState('amount')
  const [outputField, setOutputField] = useState('approved')
  const [operator, setOperator] = useState<'<' | '<=' | '==' | '!=' | '>=' | '>'>('<=')
  const [threshold, setThreshold] = useState('1000')
  const [deployment, setDeployment] = useState<'python_code' | 'python_service' | 'typescript_node'>('python_code')
  const [dependencyProfile, setDependencyProfile] = useState<'core' | 'dates' | 'validation'>('core')
  const [fallbackReason, setFallbackReason] = useState<'' | 'python_runtime_unavailable' | 'service_network_forbidden' | 'native_installation_required'>('')
  const [operationSpec, setOperationSpec] = useState<NonNullable<ProcessStep['customLogic']>['operationSpec']>()
  const [validation, setValidation] = useState<PythonCodeValidation | null>(null)
  const [localError, setLocalError] = useState('')

  useEffect(() => {
    const logic = step?.customLogic
    setReason(logic?.reasonStandardNodesInsufficient ?? '')
    setSource(logic?.source ?? DEFAULT_PYTHON_SOURCE)
    setRuleIds(logic?.businessRuleIds ?? [])
    setInputExample(JSON.stringify(logic?.inputExample ?? [], null, 2))
    setOutputExample(JSON.stringify(logic?.outputExample ?? [], null, 2))
    setErrorExample(JSON.stringify(logic?.errorExample ?? [{ json: {} }], null, 2))
    setExpectedError(logic?.expectedError ?? 'ValueError')
    setDeployment(logic?.strategy === 'python_service' ? 'python_service' : logic?.strategy === 'typescript_node' ? 'typescript_node' : 'python_code')
    setDependencyProfile(logic?.dependencyProfile ?? 'core')
    setFallbackReason(logic?.fallbackReason ?? '')
    setOperationSpec(logic?.operationSpec)
    setErrorCases((logic?.errorCases ?? ['Malformed input is rejected']).join('\n'))
    setValidation(null)
    setLocalError('')
  }, [step])

  if (!step) return <div className="properties-panel empty-properties"><Code2 size={24} /><strong>{t('selectCodeStep')}</strong><span>{t('selectCodeStepHint')}</span></div>
  if (!['system_task', 'decision'].includes(step.type)) return <div className="properties-panel empty-properties"><Code2 size={24} /><strong>{t('codeStepUnavailable')}</strong><span>{t('codeStepUnavailableHint')}</span></div>

  const rules = project.current_revision.process_ir.businessRules.filter((rule) => rule.appliesToStepIds.includes(step.id) && rule.source.trim())
  const invalidate = () => { setValidation(null); setLocalError('') }
  const parse = (value: string, label: string) => {
    try { return JSON.parse(value) as unknown }
    catch { throw new Error(t('invalidJsonExample').replace('{field}', label)) }
  }
  const artifact = (): NonNullable<ProcessStep['customLogic']> => ({
    strategy: deployment, reasonStandardNodesInsufficient: reason.trim(), businessRuleIds: ruleIds,
    runtimeProfile: deployment === 'python_service' ? 'external_python_service' : deployment === 'typescript_node' ? 'native_typescript_node' : 'n8n_native_python', source, inputExample: parse(inputExample, t('codeInputExample')),
    outputExample: parse(outputExample, t('codeOutputExample')), errorExample: parse(errorExample, t('codeErrorExample')),
    expectedError, errorCases: errorCases.split('\n').map((item) => item.trim()).filter(Boolean),
    prohibitions: ['network', 'filesystem', 'credentials', 'dynamic_code'], generatorVersion: 'python-code/1.1',
    contentHash: `sha256:${'0'.repeat(64)}`, approvalStatus: 'draft',
    ...(deployment === 'python_service' ? { dependencyProfile } : {}),
    ...(deployment === 'typescript_node' && fallbackReason && operationSpec ? { fallbackReason, operationSpec } : {}),
  })
  const validate = async () => {
    setLocalError(''); setValidation(null)
    try { setValidation(await api.validatePythonCode(project.current_revision.process_ir, step.id, '2.32', artifact())) }
    catch (reasonValue) { setLocalError(reasonValue instanceof Error ? reasonValue.message : t('error')) }
  }
  const generate = async () => {
    setLocalError(''); setValidation(null)
    const selectedRuleId = ruleIds[0] ?? rules[0]?.id
    const numericThreshold = Number(threshold)
    if (!selectedRuleId || !reason.trim() || !inputField.trim() || !outputField.trim() || !Number.isFinite(numericThreshold)) {
      setLocalError(t('codeGeneratorIncomplete')); return
    }
    try {
      const result = await api.generatePythonCode(project.current_revision.process_ir, step.id, selectedRuleId, reason.trim(), inputField.trim(), outputField.trim(), operator, numericThreshold)
      const logic = result.artifact
      setRuleIds(logic.businessRuleIds); setSource(logic.source)
      setInputExample(JSON.stringify(logic.inputExample, null, 2)); setOutputExample(JSON.stringify(logic.outputExample, null, 2))
      setErrorExample(JSON.stringify(logic.errorExample, null, 2)); setExpectedError(logic.expectedError); setErrorCases(logic.errorCases.join('\n'))
      setOperationSpec(logic.operationSpec)
    } catch (reasonValue) { setLocalError(reasonValue instanceof Error ? reasonValue.message : t('error')) }
  }
  const save = async (approved: boolean) => {
    if (!validation?.valid) return
    const customLogic = { ...validation.artifact, approvalStatus: approved ? 'approved' as const : 'draft' as const }
    await onSave({ ...step, automationHint: { target: 'n8n', nodeType: customLogic.strategy === 'typescript_node' ? 'apa.numericThreshold' : customLogic.strategy === 'python_service' ? 'n8n-nodes-base.httpRequest' : 'n8n-nodes-base.code' }, customLogic })
  }
  const toggleRule = (id: string) => { invalidate(); setRuleIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]) }
  const approved = step.customLogic?.approvalStatus === 'approved'
  return <div className="properties-panel property-form custom-code-editor" data-testid="custom-code-editor">
    <div className="property-heading"><span className="step-type">Python · n8n</span><h2>{t('customCode')}</h2><p>{t('customCodeHint')}</p></div>
    <fieldset><legend>{t('codeDeployment')}</legend><div className="property-form__choices"><label><input type="radio" name="python-deployment" checked={deployment === 'python_code'} onChange={() => { invalidate(); setDeployment('python_code') }} /><span>{t('codeDeploymentN8n')}<small>{t('codeDeploymentN8nHint')}</small></span></label><label><input type="radio" name="python-deployment" checked={deployment === 'python_service'} onChange={() => { invalidate(); setDeployment('python_service') }} /><span>{t('codeDeploymentService')}<small>{t('codeDeploymentServiceHint')}</small></span></label><label><input type="radio" name="python-deployment" checked={deployment === 'typescript_node'} onChange={() => { invalidate(); setDeployment('typescript_node') }} /><span>{t('codeDeploymentTypeScript')}<small>{t('codeDeploymentTypeScriptHint')}</small></span></label></div></fieldset>
    {deployment === 'python_service' && <label><span>{t('dependencyProfile')}</span><select value={dependencyProfile} onChange={(event) => { invalidate(); setDependencyProfile(event.target.value as typeof dependencyProfile) }}><option value="core">{t('dependencyCore')}</option><option value="dates">{t('dependencyDates')}</option><option value="validation">{t('dependencyValidation')}</option></select><small>{t(`dependencyHint_${dependencyProfile}` as Parameters<typeof t>[0])}</small></label>}
    {deployment === 'typescript_node' && <label><span>{t('fallbackReason')}</span><select value={fallbackReason} onChange={(event) => { invalidate(); setFallbackReason(event.target.value as typeof fallbackReason) }}><option value="">{t('selectFallbackReason')}</option><option value="python_runtime_unavailable">{t('fallbackPythonUnavailable')}</option><option value="service_network_forbidden">{t('fallbackNetworkForbidden')}</option><option value="native_installation_required">{t('fallbackNativeRequired')}</option></select><small>{operationSpec ? t('fallbackSpecReady') : t('fallbackSpecMissing')}</small></label>}
    {approved && <div className="code-approval code-approval--approved"><Check size={16} /><span><strong>{t('codeApproved')}</strong><small>{step.customLogic?.contentHash.slice(7, 19)}</small></span></div>}
    <label><span>{t('codeReason')}</span><textarea rows={3} value={reason} onChange={(event) => { invalidate(); setReason(event.target.value) }} /></label>
    <fieldset><legend>{t('codeRules')}</legend><div className="property-form__choices">{rules.length ? rules.map((rule) => <label key={rule.id}><input type="checkbox" checked={ruleIds.includes(rule.id)} onChange={() => toggleRule(rule.id)} /><span>{rule.name}<small>{rule.source}</small></span></label>) : <span className="code-empty-rules">{t('codeRulesMissing')}</span>}</div></fieldset>
    <section className="code-generator"><div><h3>{t('codeGenerator')}</h3><p>{t('codeGeneratorHint')}</p></div><div className="property-form__grid"><label><span>{t('codeInputField')}</span><input value={inputField} onChange={(event) => { invalidate(); setInputField(event.target.value) }} /></label><label><span>{t('codeOutputField')}</span><input value={outputField} onChange={(event) => { invalidate(); setOutputField(event.target.value) }} /></label><label><span>{t('codeOperator')}</span><select value={operator} onChange={(event) => { invalidate(); setOperator(event.target.value as typeof operator) }}>{['<', '<=', '==', '!=', '>=', '>'].map((item) => <option key={item}>{item}</option>)}</select></label><label><span>{t('codeThreshold')}</span><input inputMode="decimal" value={threshold} onChange={(event) => { invalidate(); setThreshold(event.target.value) }} /></label></div><button type="button" className="button button--secondary" disabled={busy || !rules.length} onClick={() => void generate()}><Code2 size={16} />{t('generateCode')}</button></section>
    <label><span>{t('pythonSource')}</span><textarea className="code-source" spellCheck={false} rows={13} value={source} onChange={(event) => { invalidate(); setSource(event.target.value) }} /></label>
    <section className="code-fixtures"><h3>{t('codeExamples')}</h3><label><span>{t('codeInputExample')}</span><textarea className="code-json" rows={4} value={inputExample} onChange={(event) => { invalidate(); setInputExample(event.target.value) }} /></label><label><span>{t('codeOutputExample')}</span><textarea className="code-json" rows={4} value={outputExample} onChange={(event) => { invalidate(); setOutputExample(event.target.value) }} /></label><label><span>{t('codeErrorExample')}</span><textarea className="code-json" rows={4} value={errorExample} onChange={(event) => { invalidate(); setErrorExample(event.target.value) }} /></label><div className="property-form__grid"><label><span>{t('codeExpectedError')}</span><select value={expectedError} onChange={(event) => { invalidate(); setExpectedError(event.target.value as typeof expectedError) }}><option>ValueError</option><option>TypeError</option><option>KeyError</option></select></label></div><label><span>{t('codeErrorCases')}</span><textarea rows={2} value={errorCases} onChange={(event) => { invalidate(); setErrorCases(event.target.value) }} /></label></section>
    {localError && <div className="code-validation-error"><AlertCircle size={15} />{localError}</div>}
    {validation && <section className={`code-validation ${validation.valid ? 'is-valid' : 'is-invalid'}`}><div><strong>{validation.valid ? t('codeChecksPassed') : t('codeChecksFailed')}</strong>{validation.valid && <code>{validation.artifact.contentHash.slice(7, 19)}</code>}</div>{Object.entries(validation.checks).map(([name, status]) => <span key={name} className={status === 'passed' ? 'is-passed' : 'is-failed'}>{status === 'passed' ? <Check size={14} /> : <X size={14} />}{t(`codeCheck_${name}` as Parameters<typeof t>[0])}</span>)}{validation.execution && <small>{t('codeExecutionTime').replace('{duration}', String(validation.execution.durationMs))}</small>}{validation.errors.map((item) => <p key={item.code}>{t(`codeError_${item.code}` as Parameters<typeof t>[0]) || item.message}</p>)}</section>}
    <div className="code-actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => void validate()}><ShieldCheck size={16} />{t('checkCode')}</button><button type="button" className="button button--secondary" disabled={busy || !validation?.valid} onClick={() => void save(false)}><Save size={16} />{t('saveCodeDraft')}</button><button type="button" className="button button--primary" disabled={busy || !validation?.valid} onClick={() => void save(true)}><Check size={16} />{t('approveCode')}</button></div>
  </div>
}

function PassportEditor({ project, rubric, busy, onSave, onConfirmClassification }: { project: Project; rubric: Rubric | null; busy: boolean; onSave: (passport: ProcessIR['passport']) => Promise<void>; onConfirmClassification: (entryIds: string[]) => Promise<void> }) {
  const { t } = useI18n()
  const passport = project.current_revision.process_ir.passport
  const [draft, setDraft] = useState(passport)
  useEffect(() => setDraft(passport), [passport])
  const changed = JSON.stringify(draft) !== JSON.stringify(passport)
  const splitLines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean)
  const firstMetric = draft.successMetrics[0] ?? { id: 'metric_primary', name: '', target: '', unit: '' }
  const setMetric = (next: typeof firstMetric) => setDraft({ ...draft, successMetrics: next.name.trim() ? [next, ...draft.successMetrics.slice(1)] : draft.successMetrics.slice(1) })
  return <div className="properties-panel property-stack"><form className="property-form" onSubmit={(event) => { event.preventDefault(); if (changed) void onSave(draft) }}>
    <div className="property-heading"><span className="step-type">Process IR 0.2</span><h2>{t('processPassport')}</h2></div>
    <label><span>{t('goal')}</span><textarea rows={3} value={draft.goal} onChange={(event) => setDraft({ ...draft, goal: event.target.value })} /></label>
    <label><span>{t('processOwner')}</span><select value={draft.ownerActorId ?? ''} onChange={(event) => setDraft({ ...draft, ownerActorId: event.target.value || null })}><option value="">—</option>{project.current_revision.process_ir.actors.filter((item) => item.type === 'human' || item.type === 'team').map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label><span>{t('startsWhen')}</span><input value={draft.startsWhen} onChange={(event) => setDraft({ ...draft, startsWhen: event.target.value })} /></label>
    <label><span>{t('endsWhen')}</span><input value={draft.endsWhen} onChange={(event) => setDraft({ ...draft, endsWhen: event.target.value })} /></label>
    <label><span>{t('inScope')}</span><textarea rows={3} value={draft.inScope.join('\n')} onChange={(event) => setDraft({ ...draft, inScope: splitLines(event.target.value) })} /></label>
    <label><span>{t('outOfScope')}</span><textarea rows={3} value={draft.outOfScope.join('\n')} onChange={(event) => setDraft({ ...draft, outOfScope: splitLines(event.target.value) })} /></label>
    <fieldset><legend>{t('successMetric')}</legend><div className="property-form__metric"><input aria-label={t('metricName')} placeholder={t('metricName')} value={firstMetric.name} onChange={(event) => setMetric({ ...firstMetric, name: event.target.value })} /><input aria-label={t('metricTarget')} placeholder={t('metricTarget')} value={firstMetric.target} onChange={(event) => setMetric({ ...firstMetric, target: event.target.value })} /><input aria-label={t('metricUnit')} placeholder={t('metricUnit')} value={firstMetric.unit} onChange={(event) => setMetric({ ...firstMetric, unit: event.target.value })} /></div></fieldset>
    <button className="button button--primary property-form__save" disabled={busy || !changed || !draft.goal.trim()}><Save size={16} />{t('saveChanges')}</button>
  </form>{rubric && <ClassificationEditor project={project} rubric={rubric} busy={busy} onConfirm={onConfirmClassification} />}</div>
}

function ClassificationEditor({ project, rubric, busy, onConfirm }: { project: Project; rubric: Rubric; busy: boolean; onConfirm: (entryIds: string[]) => Promise<void> }) {
  const { t } = useI18n()
  const classification = project.current_revision.process_ir.classification
  const initialSelected = useCallback(() => Object.fromEntries(rubric.dimensions.map((dimension) => [dimension.id, classification?.entryIds.find((id) => dimension.entries.some((entry) => entry.id === id)) ?? ''])), [classification, rubric])
  const [selected, setSelected] = useState<Record<string, string>>(initialSelected)
  useEffect(() => setSelected(initialSelected()), [initialSelected, project.current_revision_id])
  const entryIds = rubric.dimensions.map((dimension) => selected[dimension.id]).filter(Boolean)
  const confirmed = classification?.status === 'confirmed'
  const unchanged = JSON.stringify(entryIds) === JSON.stringify(classification?.entryIds ?? [])
  return <section className="classification-editor" data-testid="classification-editor">
    <div className="property-heading"><span className="step-type">{rubric.version}</span><h2>{t('processClassification')}</h2></div>
    <p>{confirmed ? t('classificationConfirmed') : t('classificationProposed')}</p>
    <div className="classification-grid">{rubric.dimensions.map((dimension) => <label key={dimension.id}><span>{dimension.name}</span><select value={selected[dimension.id] ?? ''} onChange={(event) => setSelected((current) => ({ ...current, [dimension.id]: event.target.value }))}><option value="">—</option>{dimension.entries.filter((entry) => !entry.deprecated).map((entry) => <option value={entry.id} key={entry.id}>{entry.name}</option>)}</select></label>)}</div>
    <button type="button" className="button button--primary" disabled={busy || entryIds.length === 0 || (confirmed && unchanged)} onClick={() => void onConfirm(entryIds)}><Check size={16} />{t('confirmClassification')}</button>
  </section>
}

function ReadinessPanel({ readiness }: { readiness: Readiness }) {
  const { locale, t } = useI18n()
  return <div className="readiness-panel"><div className="readiness-summary"><div className={`score-ring score-ring--${readiness.draft_ready ? 'ok' : 'warning'}`} style={{ '--score': `${readiness.overall * 3.6}deg` } as React.CSSProperties}><strong>{readiness.overall}</strong><small>/ 100</small></div><div><span className="section-label">{t('overall')}</span><h2>{readiness.draft_ready ? t('automationReady') : `${readiness.blocking_question_count} ${t('blockers').toLowerCase()}`}</h2></div></div>
    {readiness.next_blocking_question && <div className="next-question"><span><ChevronRight size={15} />{t('nextQuestion')}</span><p>{readiness.next_blocking_question.question}</p></div>}
    <div className="category-list">{Object.entries(readiness.categories).map(([key, category]) => <div className="category-row" key={key}><div><span>{t(`category_${key}` as Parameters<typeof t>[0])}</span><strong>{category.score}%</strong></div><span className={`progress progress--${category.status}`}><i style={{ width: `${category.score}%` }} /></span>{category.reason_codes.length > 0 && <small>{category.reason_codes.map((code) => readinessReason(code, locale)).join(' · ')}</small>}</div>)}</div>
  </div>
}

function AgentReadinessPanel({ readiness }: { readiness: AgentReadiness }) {
  const { t } = useI18n()
  return <div className="readiness-panel"><div className="readiness-summary"><div className={`score-ring score-ring--${readiness.agentReady ? 'ok' : 'warning'}`} style={{ '--score': `${readiness.overall * 3.6}deg` } as React.CSSProperties}><strong>{readiness.overall}</strong><small>/ 100</small></div><div><span className="section-label">{t('agentReadiness')}</span><h2>{readiness.agentReady ? t('agentReady') : `${readiness.blockers.length} ${t('agentBlockers')}`}</h2></div></div>
    {readiness.blockers.length > 0 && <div className="next-question"><span><ChevronRight size={15} />{t('needsClarification')}</span><p>{readiness.blockers.map((item) => t(`agentBlocker_${item}` as Parameters<typeof t>[0])).join(' · ')}</p></div>}
    <div className="category-list">{Object.entries(readiness.categories).map(([key, category]) => <div className="category-row" key={key}><div><span>{t(`agentCategory_${key}` as Parameters<typeof t>[0])}</span><strong>{category.score}%</strong></div><span className={`progress progress--${category.status}`}><i style={{ width: `${category.score}%` }} /></span></div>)}</div>
  </div>
}

function AgentContractPanel({ project, busy, onSave }: { project: Project; busy: boolean; onSave: (step: ProcessStep) => Promise<void> }) {
  const { t } = useI18n()
  const agentSteps = project.current_revision.process_ir.steps.filter((item) => item.execution.performedBy === 'ai')
  const [selectedId, setSelectedId] = useState(agentSteps[0]?.id ?? '')
  const selected = agentSteps.find((item) => item.id === selectedId) ?? agentSteps[0] ?? null
  const [draft, setDraft] = useState<ProcessStep | null>(selected)
  useEffect(() => setDraft(selected), [selected])
  if (!selected || !draft) return <div className="readiness-panel agent-contract-empty"><ShieldCheck size={24} /><h2>{t('noAgentTasks')}</h2><p>{t('noAgentTasksHint')}</p></div>
  const defaultConfig = {
    knowledgeSources: [], allowedStateIds: [], stopConditions: [], auditEvents: [],
    escalation: { missingSource: '', conflictingSources: '', lowConfidence: '', riskyAction: '' },
  }
  const config = draft.agentConfig ?? defaultConfig
  const changed = JSON.stringify(draft) !== JSON.stringify(selected)
  const splitLines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean)
  const updateConfig = (next: Partial<NonNullable<ProcessStep['agentConfig']>>) => setDraft({ ...draft, agentConfig: { ...config, ...next } })
  const toggleData = (field: 'inputs' | 'outputs', id: string) => setDraft({ ...draft, [field]: draft[field].includes(id) ? draft[field].filter((item) => item !== id) : [...draft[field], id] })
  const toggleState = (id: string) => updateConfig({ allowedStateIds: config.allowedStateIds.includes(id) ? config.allowedStateIds.filter((item) => item !== id) : [...config.allowedStateIds, id] })
  return <form className="properties-panel property-form agent-contract-editor" onSubmit={(event) => { event.preventDefault(); if (changed) void onSave(draft) }}>
    <div className="property-heading"><span className="step-type">Agent Contract 1.1</span><h2>{t('agentContract')}</h2><p>{t('agentContractHint')}</p></div>
    {agentSteps.length > 1 && <label><span>{t('agentTask')}</span><select value={selected.id} onChange={(event) => setSelectedId(event.target.value)}>{agentSteps.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>}
    <section className="agent-contract-section"><h3>{t('agentRoleAndGoal')}</h3><label><span>{t('agentRole')}</span><input value={draft.title} required onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>{t('agentGoal')}</span><textarea rows={3} value={draft.description} required onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label></section>
    <section className="agent-contract-section"><h3>{t('agentToolAccess')}</h3><div className="property-form__grid"><label><span>{t('system')}</span><select value={draft.systemId ?? ''} onChange={(event) => setDraft({ ...draft, systemId: event.target.value || null })}><option value="">—</option>{project.current_revision.process_ir.systems.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>{t('agentOperation')}</span><input value={draft.operation.name} required onChange={(event) => setDraft({ ...draft, operation: { ...draft.operation, name: event.target.value } })} /></label></div><div className="property-form__grid"><label><span>{t('autonomy')}</span><select value={draft.execution.autonomy} onChange={(event) => { const autonomy = event.target.value as ProcessStep['execution']['autonomy']; setDraft({ ...draft, execution: { ...draft.execution, autonomy, approvalRequired: autonomy === 'supervised' || draft.execution.approvalRequired } }) }}><option value="assist">{t('autonomyAssist')}</option><option value="supervised">{t('autonomySupervised')}</option><option value="autonomous">{t('autonomyAutonomous')}</option></select></label><label className="property-form__check agent-contract-check"><input type="checkbox" checked={draft.execution.approvalRequired} disabled={draft.execution.autonomy === 'supervised'} onChange={(event) => setDraft({ ...draft, execution: { ...draft.execution, approvalRequired: event.target.checked } })} /><span>{t('approvalRequired')}</span></label></div><label><span>{t('agentProhibited')}</span><textarea rows={3} value={draft.execution.restrictions.join('\n')} onChange={(event) => setDraft({ ...draft, execution: { ...draft.execution, restrictions: splitLines(event.target.value) } })} /></label></section>
    <section className="agent-contract-section"><h3>{t('agentDataAndKnowledge')}</h3>{(['inputs', 'outputs'] as const).map((field) => <fieldset key={field}><legend>{t(field)}</legend><div className="property-form__choices">{project.current_revision.process_ir.dataObjects.length ? project.current_revision.process_ir.dataObjects.map((item) => <label key={item.id}><input type="checkbox" checked={draft[field].includes(item.id)} onChange={() => toggleData(field, item.id)} /><span>{item.name}</span></label>) : <span>—</span>}</div></fieldset>)}<label><span>{t('knowledgeSources')}</span><textarea rows={3} placeholder={t('knowledgeSourcesHint')} value={config.knowledgeSources.join('\n')} onChange={(event) => updateConfig({ knowledgeSources: splitLines(event.target.value) })} /></label></section>
    <section className="agent-contract-section"><h3>{t('agentControl')}</h3>{project.current_revision.process_ir.states.length > 0 && <fieldset><legend>{t('allowedStates')}</legend><div className="property-form__choices">{project.current_revision.process_ir.states.map((item) => <label key={item.id}><input type="checkbox" checked={config.allowedStateIds.includes(item.id)} onChange={() => toggleState(item.id)} /><span>{item.name}</span></label>)}</div></fieldset>}<label><span>{t('stopConditions')}</span><textarea rows={3} value={config.stopConditions.join('\n')} onChange={(event) => updateConfig({ stopConditions: splitLines(event.target.value) })} /></label></section>
    <section className="agent-contract-section"><h3>{t('agentEscalation')}</h3><div className="agent-escalation-grid">{(['missingSource', 'conflictingSources', 'lowConfidence', 'riskyAction'] as const).map((field) => <label key={field}><span>{t(`escalation_${field}` as Parameters<typeof t>[0])}</span><input value={config.escalation[field]} onChange={(event) => updateConfig({ escalation: { ...config.escalation, [field]: event.target.value } })} /></label>)}</div></section>
    <section className="agent-contract-section"><h3>{t('agentAudit')}</h3><label><span>{t('auditEvents')}</span><textarea rows={3} value={config.auditEvents.join('\n')} onChange={(event) => updateConfig({ auditEvents: splitLines(event.target.value) })} /></label></section>
    <button className="button button--primary property-form__save" disabled={busy || !changed || !draft.title.trim() || !draft.description.trim()}><Save size={16} />{t('saveAgentContract')}</button>
  </form>
}

function HistoryDrawer({ revisions, currentId, busy, onRestore, onClose }: { revisions: Revision[]; currentId: string; busy: boolean; onRestore: (id: string) => void; onClose: () => void }) {
  const { locale, t } = useI18n()
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="history-drawer"><div className="drawer-header"><div><span className="section-label">Process IR</span><h2>{t('revisionHistory')}</h2></div><button className="icon-button" onClick={onClose} title={t('close')} aria-label={t('close')}><X size={18} /></button></div><div className="revision-list">{[...revisions].reverse().map((revision) => <div className={`revision-item ${revision.id === currentId ? 'is-current' : ''}`} key={revision.id}><span className="revision-marker"><FileClock size={16} /></span><div><div className="revision-item__head"><strong>v{revision.version_number}</strong><span className={`revision-perspective revision-perspective--${revision.perspective}`}>{t(revision.perspective === 'as_is' ? 'asIs' : 'toBe')}</span>{revision.id === currentId && <span>{t('current')}</span>}</div><p>{t(`source_${revision.source}` as Parameters<typeof t>[0]) || revision.source}</p><time>{new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(revision.created_at))}</time>{revision.id !== currentId && <button className="text-button" disabled={busy} onClick={() => onRestore(revision.id)}><RotateCcw size={14} />{t('restore')}</button>}</div></div>)}</div></aside></div>
}

function AgentRunsDrawer({ runs, busy, onResolve, onReplay, onClose }: { runs: AgentRun[]; busy: boolean; onResolve: (incidentId: string) => void; onReplay: (incidentId: string, revision: 'original' | 'current') => void; onClose: () => void }) {
  const { locale, t } = useI18n()
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="history-drawer agent-runs-drawer"><div className="drawer-header"><div><span className="section-label">Agent Contract 1.1</span><h2>{t('agentRunHistory')}</h2></div><button className="icon-button" onClick={onClose} title={t('close')} aria-label={t('close')}><X size={18} /></button></div><div className="revision-list">{runs.length === 0 ? <div className="agent-runs-empty"><Activity size={22} /><strong>{t('noAgentRuns')}</strong><span>{t('noAgentRunsHint')}</span></div> : runs.map((run) => <AgentRunItem key={run.id} run={run} busy={busy} locale={locale} t={t} onResolve={onResolve} onReplay={onReplay} />)}</div></aside></div>
}

function AgentRunItem({ run, busy, locale, t, onResolve, onReplay }: { run: AgentRun; busy: boolean; locale: string; t: ReturnType<typeof useI18n>['t']; onResolve: (incidentId: string) => void; onReplay: (incidentId: string, revision: 'original' | 'current') => void }) {
  const [revision, setRevision] = useState<'original' | 'current'>('original')
  const category = run.incident_category ? t(`incidentCategory_${run.incident_category}` as Parameters<typeof t>[0]) : ''
  return <article className="agent-run-item"><div className="agent-run-item__head"><strong>{run.runtime === 'openclaw' ? 'OpenClaw' : 'Hermes'}</strong><span className={`agent-run-status agent-run-status--${run.status}`}>{t(`agentRunStatus_${run.status}` as Parameters<typeof t>[0])}</span></div>{run.dispatch_status && <div className={`dispatch-state dispatch-state--${run.dispatch_status}`}><Activity size={13} /><span>{t(`dispatchStatus_${run.dispatch_status}` as Parameters<typeof t>[0])}</span>{run.dispatch_attempts > 0 && <small>{t('dispatchAttempt')} {run.dispatch_attempts}</small>}</div>}<time>{new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(run.created_at))}</time><div className="agent-run-usage"><span>{t('agentRunSteps')}: {run.usage.steps}/{run.limits.max_steps}</span><span>{t('agentRunTools')}: {run.usage.tool_calls}/{run.limits.max_tool_calls}</span><span>{t('agentRunTimeout')}: {run.limits.timeout_seconds}s</span></div>{run.incident_id && <section className={`agent-incident agent-incident--${run.incident_status}`}><div><AlertCircle size={16} /><strong>{t('agentIncident')}</strong><span>{t(`incidentStatus_${run.incident_status}` as Parameters<typeof t>[0])}</span></div><p>{category}</p>{run.incident_reason_code && <code>{run.incident_reason_code}</code>}{run.incident_status === 'open' && <><label>{t('replayRevision')}<select value={revision} onChange={(event) => setRevision(event.target.value as 'original' | 'current')} disabled={busy}><option value="original">{t('originalRunRevision')}</option><option value="current">{t('currentProjectRevision')}</option></select></label><div className="agent-incident__actions"><button className="button button--secondary button--compact" disabled={busy} onClick={() => onResolve(run.incident_id!)}>{t('closeWithoutReplay')}</button><button className="button button--primary button--compact" disabled={busy} onClick={() => onReplay(run.incident_id!, revision)}><RotateCcw size={14} />{t('replayRun')}</button></div></>}</section>}<div className="agent-run-events">{run.events.map((event) => <span key={event.id}><i />{t(`agentRunEvent_${event.event_type}` as Parameters<typeof t>[0])}{event.reason_code ? ` · ${event.reason_code}` : ''}</span>)}</div></article>
}

function PilotGateDrawer({ gate, evaluations, runtime, busy, onRuntime, onApprove, onDispatch, onClose }: { gate: AgentPilotGate; evaluations: AgentEvaluationRun[]; runtime: 'openclaw' | 'hermes'; busy: boolean; onRuntime: (value: 'openclaw' | 'hermes') => void; onApprove: () => void; onDispatch: () => void; onClose: () => void }) {
  const { locale, t } = useI18n()
  const canApprove = gate.latest_evaluation?.status === 'passed' && gate.baseline?.evaluation_run_id !== gate.latest_evaluation.id
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="history-drawer pilot-gate-drawer"><div className="drawer-header"><div><span className="section-label">Agent Contract 1.1</span><h2>{t('pilotGate')}</h2></div><button className="icon-button" onClick={onClose} title={t('close')} aria-label={t('close')}><X size={18} /></button></div><div className="pilot-gate-body"><div className="segmented-control segmented-control--two"><button className={runtime === 'openclaw' ? 'is-active' : ''} disabled={busy} onClick={() => onRuntime('openclaw')}>OpenClaw</button><button className={runtime === 'hermes' ? 'is-active' : ''} disabled={busy} onClick={() => onRuntime('hermes')}>Hermes</button></div><section className={`pilot-gate-summary pilot-gate-summary--${gate.pilot_ready ? 'ready' : gate.status}`}><ShieldCheck size={24} /><div><span>{t(`pilotStatus_${gate.status}` as Parameters<typeof t>[0])}</span><strong>{gate.pilot_ready ? t('pilotReady') : t('pilotBlocked')}</strong><small>{t(`pilotHint_${gate.status}` as Parameters<typeof t>[0])}</small></div></section><div className="pilot-gate-metrics"><span><strong>{gate.latest_evaluation?.passed_count ?? 0}/{gate.required_scenarios.length}</strong>{t('pilotScenarios')}</span><span><strong>{evaluations.length}</strong>{t('pilotChecks')}</span><span><strong>{gate.baseline ? t('yes') : t('no')}</strong>{t('pilotBaseline')}</span></div>{canApprove && <button className="button button--primary pilot-approve" disabled={busy} onClick={onApprove}><Check size={16} />{t('approveBaseline')}</button>}{gate.pilot_ready && <button className="button button--primary pilot-dispatch" disabled={busy} onClick={onDispatch}><Activity size={16} />{t('startAgentPilot')}</button>}<div className="pilot-evaluation-list"><span className="section-label">{t('evaluationHistory')}</span>{evaluations.length === 0 ? <p>{t('noEvaluations')}</p> : evaluations.map((item) => <article key={item.id}><span className={`agent-run-status agent-run-status--${item.status === 'passed' ? 'completed' : 'failed'}`}>{t(item.status === 'passed' ? 'evaluationPassed' : 'evaluationFailed')}</span><strong>{item.passed_count}/{item.total_count} · {(item.duration_ms / 1000).toFixed(1)}s</strong><time>{new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}</time>{gate.baseline?.evaluation_run_id === item.id && <small><Check size={12} />{t('currentBaseline')}</small>}</article>)}</div></div></aside></div>
}

const APP_SPEC_TARGETS: Array<{ id: AppSpecTarget; name: string }> = [
  { id: 'codex', name: 'Codex / ChatGPT' },
  { id: 'cursor', name: 'Cursor' },
  { id: 'google_ai_studio', name: 'Google AI Studio' },
  { id: 'bolt', name: 'Bolt.new' },
  { id: 'generic', name: 'Universal' },
]

const AGENT_TARGETS: Array<{ id: AgentTarget; name: string }> = [
  { id: 'openclaw', name: 'OpenClaw' },
  { id: 'hermes', name: 'Hermes' },
  { id: 'langgraph', name: 'LangGraph' },
  { id: 'crewai', name: 'CrewAI' },
  { id: 'agno', name: 'Agno' },
]
const OPENCLAW_VERSIONS: OpenClawVersion[] = ['2026.8.2', '2026.8.1', '2026.7.1']

function ExportModal({ project, format, setFormat, appTarget, setAppTarget, n8nTarget, setN8nTarget, includeN8nGuide, setIncludeN8nGuide, agentTarget, setAgentTarget, openclawVersion, setOpenclawVersion, readiness, agentReadiness, roundTrip, perspective, busy, onClose, onDownload }: {
  project: Project; format: ExportFormat; setFormat: (value: ExportFormat) => void;
  appTarget: AppSpecTarget; setAppTarget: (value: AppSpecTarget) => void;
  n8nTarget: string; setN8nTarget: (value: string) => void;
  includeN8nGuide: boolean; setIncludeN8nGuide: (value: boolean) => void;
  agentTarget: AgentTarget; setAgentTarget: (value: AgentTarget) => void;
  openclawVersion: OpenClawVersion; setOpenclawVersion: (value: OpenClawVersion) => void;
  readiness: Readiness; agentReadiness: AgentReadiness | null; roundTrip: boolean; perspective: 'as_is' | 'to_be'; busy: boolean; onClose: () => void; onDownload: () => void
}) {
  const { t } = useI18n()
  const [profiles, setProfiles] = useState<RuntimeConnectionProfile[]>([])
  const [publications, setPublications] = useState<N8nPublication[]>([])
  const [profileId, setProfileId] = useState('')
  const [publicationPreview, setPublicationPreview] = useState<N8nPublicationPreview | null>(null)
  const [publicationBusy, setPublicationBusy] = useState(false)
  const [publicationError, setPublicationError] = useState('')
  const [agentDeliveries, setAgentDeliveries] = useState<AgentPackageDelivery[]>([])
  const [agentProfileId, setAgentProfileId] = useState('')
  const [agentDeliveryPreview, setAgentDeliveryPreview] = useState<AgentPackageDeliveryPreview | null>(null)
  const [agentDeliveryBusy, setAgentDeliveryBusy] = useState(false)
  const [agentDeliveryError, setAgentDeliveryError] = useState('')
  const description = format === 'spec' ? t('exportSpecText') : format === 'bpmn' ? t('exportBpmnText') : format === 'agent' ? t('exportAgentText') : t('exportN8nText')
  const downloadLabel = format === 'spec' ? t('downloadSpec') : format === 'bpmn' ? t('downloadBpmn') : format === 'agent' ? t('downloadAgent') : t('downloadN8n')
  const matchingProfiles = profiles.filter((profile) => profile.kind === 'n8n' && profile.status === 'verified' && profile.n8n_minor === n8nTarget)
  const currentPublication = publications.find((item) => item.profile_id === profileId && item.revision_id === project.current_revision_id && item.remote_workflow_id && ['published', 'failed', 'deletion_failed'].includes(item.status)) ?? null
  const directAgentTarget = agentTarget === 'openclaw' || agentTarget === 'hermes'
  const matchingAgentProfiles = directAgentTarget ? profiles.filter((profile) => profile.kind === agentTarget && profile.status === 'verified') : []
  const currentAgentDelivery = agentDeliveries.find((item) => item.profile_id === agentProfileId && item.revision_id === project.current_revision_id && item.remote_package_id && ['stored', 'failed', 'deletion_failed'].includes(item.status)) ?? null

  useEffect(() => {
    let active = true
    Promise.all([api.runtimeConnections(project.workspace_id), api.n8nPublications(project.id), api.agentPackageDeliveries(project.id)])
      .then(([nextProfiles, nextPublications, nextDeliveries]) => { if (active) { setProfiles(nextProfiles); setPublications(nextPublications); setAgentDeliveries(nextDeliveries) } })
      .catch(() => undefined)
    return () => { active = false }
  }, [project.id, project.workspace_id])

  useEffect(() => {
    const available = profiles.filter((profile) => profile.kind === 'n8n' && profile.status === 'verified' && profile.n8n_minor === n8nTarget)
    setProfileId((current) => available.some((profile) => profile.id === current) ? current : available[0]?.id ?? '')
    setPublicationPreview(null)
    setPublicationError('')
  }, [n8nTarget, profiles])

  useEffect(() => {
    const available = directAgentTarget ? profiles.filter((profile) => profile.kind === agentTarget && profile.status === 'verified') : []
    setAgentProfileId((current) => available.some((profile) => profile.id === current) ? current : available[0]?.id ?? '')
    setAgentDeliveryPreview(null)
    setAgentDeliveryError('')
  }, [agentTarget, directAgentTarget, profiles])

  function publicationErrorText(reason: unknown) {
    if (!(reason instanceof ApiError)) return t('error')
    const keys: Partial<Record<string, Parameters<typeof t>[0]>> = {
      publication_preview_stale: 'publicationError_previewStale', n8n_profile_not_verified: 'publicationError_profileNotVerified',
      authentication_failed: 'publicationError_authentication', publication_timeout: 'publicationError_timeout',
      n8n_publication_rejected: 'publicationError_rejected', n8n_unavailable: 'publicationError_unavailable',
      remote_workflow_not_inactive: 'publicationError_active', revision_conflict: 'publicationError_revision',
    }
    const key = keys[reason.code ?? '']
    return key ? t(key) : reason.message
  }

  async function previewPublication() {
    if (!profileId) return
    setPublicationBusy(true); setPublicationError('')
    try { setPublicationPreview(await api.previewN8nPublication(project.id, profileId, project.current_revision_id)) }
    catch (reason) { setPublicationError(publicationErrorText(reason)) }
    finally { setPublicationBusy(false) }
  }

  async function publishPublication() {
    if (!profileId || !publicationPreview) return
    setPublicationBusy(true); setPublicationError('')
    try {
      const published = await api.publishN8n(project.id, profileId, project.current_revision_id, publicationPreview.workflow_sha256)
      setPublications((current) => [published, ...current.filter((item) => item.id !== published.id)])
    } catch (reason) {
      setPublicationError(publicationErrorText(reason))
      api.n8nPublications(project.id).then(setPublications).catch(() => undefined)
    }
    finally { setPublicationBusy(false) }
  }

  async function removePublication() {
    if (!currentPublication) return
    if (!window.confirm(t('removeFromN8nConfirm'))) return
    setPublicationBusy(true); setPublicationError('')
    try {
      const deleted = await api.deleteN8nPublication(currentPublication.id)
      setPublications((current) => current.map((item) => item.id === deleted.id ? deleted : item))
      setPublicationPreview(null)
    } catch (reason) { setPublicationError(publicationErrorText(reason)) }
    finally { setPublicationBusy(false) }
  }

  function agentDeliveryErrorText(reason: unknown) {
    if (!(reason instanceof ApiError)) return t('error')
    const keys: Partial<Record<string, Parameters<typeof t>[0]>> = {
      agent_delivery_preview_stale: 'agentDeliveryError_previewStale', agent_profile_not_verified: 'agentDeliveryError_profileNotVerified',
      agent_package_not_ready: 'agentDeliveryError_notReady', agent_mode_required: 'agentDeliveryError_modeRequired',
      authentication_failed: 'publicationError_authentication', agent_delivery_timeout: 'agentDeliveryError_timeout',
      agent_package_rejected: 'agentDeliveryError_rejected', agent_runtime_unavailable: 'agentDeliveryError_unavailable',
      remote_agent_package_not_inactive: 'agentDeliveryError_active', revision_conflict: 'publicationError_revision',
    }
    const key = keys[reason.code ?? '']
    return key ? t(key) : reason.message
  }

  async function previewAgentDelivery() {
    if (!agentProfileId) return
    setAgentDeliveryBusy(true); setAgentDeliveryError('')
    try { setAgentDeliveryPreview(await api.previewAgentPackageDelivery(project.id, agentProfileId, project.current_revision_id)) }
    catch (reason) { setAgentDeliveryError(agentDeliveryErrorText(reason)) }
    finally { setAgentDeliveryBusy(false) }
  }

  async function deliverAgentPackage() {
    if (!agentProfileId || !agentDeliveryPreview) return
    setAgentDeliveryBusy(true); setAgentDeliveryError('')
    try {
      const delivered = await api.deliverAgentPackage(project.id, agentProfileId, project.current_revision_id, agentDeliveryPreview.package_sha256)
      setAgentDeliveries((current) => [delivered, ...current.filter((item) => item.id !== delivered.id)])
    } catch (reason) {
      setAgentDeliveryError(agentDeliveryErrorText(reason))
      api.agentPackageDeliveries(project.id).then(setAgentDeliveries).catch(() => undefined)
    }
    finally { setAgentDeliveryBusy(false) }
  }

  async function removeAgentDelivery() {
    if (!currentAgentDelivery) return
    if (!window.confirm(t('removeAgentPackageConfirm'))) return
    setAgentDeliveryBusy(true); setAgentDeliveryError('')
    try {
      const deleted = await api.deleteAgentPackageDelivery(currentAgentDelivery.id)
      setAgentDeliveries((current) => current.map((item) => item.id === deleted.id ? deleted : item))
      setAgentDeliveryPreview(null)
    } catch (reason) { setAgentDeliveryError(agentDeliveryErrorText(reason)) }
    finally { setAgentDeliveryBusy(false) }
  }

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal export-modal"><div className="modal__header"><div><span className="section-label">Spec · BPMN · n8n · Agent</span><h2>{t('exportTitle')}</h2></div><button className="icon-button" onClick={onClose} title={t('close')} aria-label={t('close')}><X size={18} /></button></div>
    <div className="export-format-control" role="tablist" aria-label={t('exportFormat')}>
      <button type="button" className={format === 'spec' ? 'is-active' : ''} onClick={() => setFormat('spec')}><FileText size={18} /><span><strong>{t('exportSpec')}</strong><small>{t('exportSpecShort')}</small></span></button>
      <button type="button" className={format === 'bpmn' ? 'is-active' : ''} onClick={() => setFormat('bpmn')}><GitBranch size={18} /><span><strong>BPMN</strong><small>draw.io</small></span></button>
      <button type="button" className={format === 'n8n' ? 'is-active' : ''} onClick={() => setFormat('n8n')}><Workflow size={18} /><span><strong>n8n</strong><small>workflow</small></span></button>
      <button type="button" className={format === 'agent' ? 'is-active' : ''} onClick={() => setFormat('agent')}><Bot size={18} /><span><strong>Agent</strong><small>runtime package</small></span></button>
    </div>
    <p className="modal__description">{description}</p>
    {format === 'n8n' && !readiness.draft_ready && <div className="export-warning"><Clock3 size={18} /><span><strong>{t('n8nConfigurationWarning')}</strong>{readiness.next_blocking_question && <small>{readiness.next_blocking_question.question}</small>}</span></div>}
    {format === 'n8n' && roundTrip && <div className="round-trip-note"><GitBranch size={17} /><span><strong>{t('roundTripExport')}</strong><small>{t(perspective === 'as_is' ? 'roundTripAsIsHint' : 'roundTripToBeHint')}</small></span></div>}
    {format === 'agent' && !agentReadiness?.agentReady && <div className="export-warning"><Clock3 size={18} /><span><strong>{t('agentConfigurationWarning')}</strong><small>{t('agentExportDraftHint')}</small></span></div>}
    {format === 'spec' && <label className="export-option">{t('appBuilder')}<select value={appTarget} onChange={(event) => setAppTarget(event.target.value as AppSpecTarget)}>{APP_SPEC_TARGETS.map((target) => <option value={target.id} key={target.id}>{target.name}</option>)}</select></label>}
    {format === 'n8n' && <div className="export-option"><span>{t('n8nVersion')}</span><span className="segmented-control">{['2.32', '2.31', '2.30'].map((version) => <button type="button" className={version === n8nTarget ? 'is-active' : ''} onClick={() => setN8nTarget(version)} key={version}>{version}</button>)}</span></div>}
    {format === 'n8n' && <label className="export-checkbox"><input type="checkbox" checked={includeN8nGuide} onChange={(event) => setIncludeN8nGuide(event.target.checked)} /><span><strong>{t('includeN8nGuide')}</strong><small>{t('includeN8nGuideHint')}</small></span></label>}
    {format === 'n8n' && <section className="n8n-publish"><div className="n8n-publish__heading"><span><strong>{t('publishToN8n')}</strong><small>{t('publishToN8nHint')}</small></span><span className="runtime-status">{t('inactiveOnly')}</span></div>{matchingProfiles.length === 0 ? <p>{t('noVerifiedN8nConnection')}</p> : <><label>{t('publishDestination')}<select value={profileId} onChange={(event) => { setProfileId(event.target.value); setPublicationPreview(null) }}>{matchingProfiles.map((profile) => <option value={profile.id} key={profile.id}>{profile.name}</option>)}</select></label>{currentPublication ? <div className={`n8n-publish__result ${currentPublication.status !== 'published' ? 'is-warning' : ''}`}><Check size={16} /><span><strong>{t(currentPublication.status === 'published' ? 'publishedInactive' : 'publicationCleanupRequired')}</strong><small>ID: {currentPublication.remote_workflow_id}</small></span><button type="button" className="button button--secondary button--small" disabled={publicationBusy} onClick={() => void removePublication()}><Trash2 size={14} />{t('removeFromN8n')}</button></div> : publicationPreview ? <div className="n8n-publish__preview"><span><strong>{publicationPreview.workflow_name}</strong><small>{t('publicationPreviewStats').replace('{nodes}', String(publicationPreview.node_count)).replace('{connections}', String(publicationPreview.connection_count))}</small><code>{publicationPreview.workflow_sha256.slice(0, 16)}…</code></span><button type="button" className="button button--primary button--small" disabled={publicationBusy} onClick={() => void publishPublication()}>{publicationBusy ? <LoaderCircle className="spin" size={14} /> : <FileUp size={14} />}{t('publishInactive')}</button></div> : <button type="button" className="button button--secondary n8n-publish__preview-button" disabled={publicationBusy} onClick={() => void previewPublication()}>{publicationBusy ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />}{t('checkBeforePublish')}</button>}</>}{publicationError && <div className="notice notice--error">{publicationError}</div>}</section>}
    {format === 'agent' && <label className="export-option">{t('agentRuntime')}<select value={agentTarget} onChange={(event) => setAgentTarget(event.target.value as AgentTarget)}>{AGENT_TARGETS.map((target) => <option value={target.id} key={target.id}>{target.name}</option>)}</select></label>}
    {format === 'agent' && agentTarget === 'openclaw' && <div className="export-option"><span>OpenClaw</span><span className="segmented-control">{OPENCLAW_VERSIONS.map((version) => <button type="button" className={version === openclawVersion ? 'is-active' : ''} onClick={() => setOpenclawVersion(version)} key={version}>{version}</button>)}</span></div>}
    {format === 'agent' && directAgentTarget && <section className="n8n-publish agent-delivery"><div className="n8n-publish__heading"><span><strong>{t('deliverAgentPackage')}</strong><small>{t('deliverAgentPackageHint')}</small></span><span className="runtime-status">{t('storedNotStarted')}</span></div>{matchingAgentProfiles.length === 0 ? <p>{t('noVerifiedAgentConnection')}</p> : <><label>{t('agentDeliveryDestination')}<select value={agentProfileId} onChange={(event) => { setAgentProfileId(event.target.value); setAgentDeliveryPreview(null) }}>{matchingAgentProfiles.map((profile) => <option value={profile.id} key={profile.id}>{profile.name}</option>)}</select></label>{currentAgentDelivery ? <div className={`n8n-publish__result ${currentAgentDelivery.status !== 'stored' ? 'is-warning' : ''}`}><Check size={16} /><span><strong>{t(currentAgentDelivery.status === 'stored' ? 'agentPackageStored' : 'agentDeliveryCleanupRequired')}</strong><small>ID: {currentAgentDelivery.remote_package_id}</small></span><button type="button" className="button button--secondary button--small" disabled={agentDeliveryBusy} onClick={() => void removeAgentDelivery()}><Trash2 size={14} />{t('removeAgentPackage')}</button></div> : agentDeliveryPreview ? <div className="n8n-publish__preview"><span><strong>{agentDeliveryPreview.process_name}</strong><small>{t('agentDeliveryPreviewStats').replace('{files}', String(agentDeliveryPreview.file_count)).replace('{size}', `${Math.ceil(agentDeliveryPreview.package_size / 1024)} KB`).replace('{score}', String(agentDeliveryPreview.readiness_score))}</small><code>{agentDeliveryPreview.package_sha256.slice(0, 16)}…</code>{!agentDeliveryPreview.ready && <small className="agent-delivery__blocked">{t('agentDeliveryBlocked').replace('{count}', String(agentDeliveryPreview.blocker_count))}</small>}</span><button type="button" className="button button--primary button--small" disabled={agentDeliveryBusy || !agentDeliveryPreview.ready} onClick={() => void deliverAgentPackage()}>{agentDeliveryBusy ? <LoaderCircle className="spin" size={14} /> : <FileUp size={14} />}{t('storeAgentPackage')}</button></div> : <button type="button" className="button button--secondary n8n-publish__preview-button" disabled={agentDeliveryBusy} onClick={() => void previewAgentDelivery()}>{agentDeliveryBusy ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />}{t('checkAgentPackage')}</button>}</>}{agentDeliveryError && <div className="notice notice--error">{agentDeliveryError}</div>}</section>}
    <div className="export-files">{format === 'spec' && <span>app-spec-{appTarget}.md</span>}{format === 'bpmn' && <span>process-bpmn.drawio</span>}{format === 'n8n' && <><span>workflow-n8n-{n8nTarget}.json</span>{roundTrip && <span>ROUND_TRIP_REPORT.json</span>}<span>PROCESS_SETUP.md</span>{includeN8nGuide && <span>N8N_BEGINNER_GUIDE.md</span>}<span>README.md</span></>}{format === 'agent' && <><span>agent-contract.json</span><span>{agentTarget}/</span><span>runtime_core/</span><span>evals/</span><span>contracts/</span></>}</div>
    <div className="modal__actions"><button className="button button--secondary" onClick={onClose}>{t('cancel')}</button><button className="button button--primary" disabled={busy} onClick={onDownload}>{busy ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}{downloadLabel}</button></div>
  </div></div>
}
