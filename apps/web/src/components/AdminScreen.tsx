import { useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, ArrowLeft, BarChart3, Building2, CircleDollarSign, ClipboardList, Coins, Download, FolderKanban, LayoutDashboard, LoaderCircle, LogOut, ServerCog, ShieldCheck, Users } from 'lucide-react'
import { api, ApiError } from '../api'
import type { AdminActivityReport, AdminAuditEvent, AdminIdentity, AdminInvoices, AdminLLMUsage, AdminUsage, AdminUser, AdminWorkspace } from '../types'
import { useI18n } from '../i18n/context'
import { Brand } from './Brand'
import { LanguageSwitch } from './LanguageSwitch'

type AdminSection = 'overview' | 'users' | 'workspaces' | 'reports' | 'billing' | 'audit'

export function AdminScreen({ identity, onBack, onLogout }: { identity: AdminIdentity; onBack: () => void; onLogout: () => void }) {
  const { locale, t } = useI18n()
  const [section, setSection] = useState<AdminSection>('overview')
  const [users, setUsers] = useState<AdminUser[]>([])
  const [workspaces, setWorkspaces] = useState<AdminWorkspace[]>([])
  const [audit, setAudit] = useState<AdminAuditEvent[]>([])
  const [llmUsage, setLlmUsage] = useState<AdminLLMUsage | null>(null)
  const [usage, setUsage] = useState<AdminUsage | null>(null)
  const [invoices, setInvoices] = useState<AdminInvoices | null>(null)
  const [activityReport, setActivityReport] = useState<AdminActivityReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([api.adminUsers(), api.adminWorkspaces(), api.adminAuditEvents(), api.adminActivityReport(), identity.capabilities.billingEnabled ? api.adminLlmUsage() : Promise.resolve(null), identity.capabilities.billingEnabled ? api.adminUsage() : Promise.resolve(null), identity.capabilities.billingEnabled ? api.adminInvoices() : Promise.resolve(null)])
      .then(([userPage, workspacePage, auditPage, report, llm, meteredUsage, invoicePage]) => {
        if (!active) return
        setUsers(userPage.items); setWorkspaces(workspacePage.items); setAudit(auditPage.items); setActivityReport(report); setLlmUsage(llm); setUsage(meteredUsage); setInvoices(invoicePage)
      })
      .catch((reason) => active && setError(reason instanceof ApiError ? reason.message : t('error')))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [identity.capabilities.billingEnabled, t])

  const projectCount = useMemo(() => workspaces.reduce((sum, item) => sum + item.projectCount, 0), [workspaces])
  const activeUsers = useMemo(() => users.filter((item) => item.isActive).length, [users])
  const date = (value: string) => new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
  const modeLabel = identity.capabilities.mode === 'hosted' ? t('adminHosted') : t('adminSelfHosted')

  const navigation: Array<{ id: AdminSection; icon: typeof LayoutDashboard; label: string }> = [
    { id: 'overview', icon: LayoutDashboard, label: t('adminOverview') },
    { id: 'users', icon: Users, label: t('adminUsers') },
    { id: 'workspaces', icon: Building2, label: t('adminWorkspaces') },
    { id: 'reports', icon: BarChart3, label: t('adminReports') },
    ...(identity.capabilities.billingEnabled ? [{ id: 'billing' as const, icon: Coins, label: t('adminAiCosts') }] : []),
    { id: 'audit', icon: ClipboardList, label: t('adminAudit') },
  ]

  return <div className="app-shell admin-shell">
    <aside className="global-sidebar">
      <Brand compact />
      <nav>
        <button className="nav-button" onClick={onBack} title={t('projects')}><FolderKanban size={19} /><span>{t('projects')}</span></button>
        <button className="nav-button is-active" title={t('admin')}><ShieldCheck size={19} /><span>{t('admin')}</span></button>
      </nav>
      <button className="nav-button global-sidebar__logout" onClick={onLogout} title={t('logout')}><LogOut size={19} /><span>{t('logout')}</span></button>
    </aside>
    <main className="admin-page" data-help-topic="admin">
      <header className="topbar admin-topbar">
        <div className="admin-title"><button className="icon-button" onClick={onBack} title={t('back')} aria-label={t('back')}><ArrowLeft size={18} /></button><div><span className="eyebrow">{t('serviceAdministration')}</span><h1>{t('admin')}</h1></div></div>
        <div className="topbar__actions"><span className={`admin-mode admin-mode--${identity.capabilities.mode}`}><ServerCog size={14} />{modeLabel}</span><LanguageSwitch /></div>
      </header>
      <div className="admin-layout">
        <nav className="admin-section-nav" aria-label={t('admin')}>
          <div className="admin-account"><span className="admin-account__mark">{identity.email.slice(0, 1).toUpperCase()}</span><span><strong>{identity.email}</strong><small>{t(`adminRole_${identity.serviceRole}`)}</small></span></div>
          {navigation.map(({ id, icon: Icon, label }) => <button key={id} className={section === id ? 'is-active' : ''} onClick={() => setSection(id)} aria-label={label} title={label}><Icon size={17} /><span>{label}</span></button>)}
        </nav>
        <section className="admin-content">
          {error && <div className="notice notice--error">{error}</div>}
          {loading ? <div className="loading-state"><LoaderCircle className="spin" size={22} />{t('loading')}</div> : <>
            {section === 'overview' && <AdminOverview identity={identity} users={users} workspaces={workspaces} audit={audit} projectCount={projectCount} activeUsers={activeUsers} date={date} />}
            {section === 'users' && <UsersTable users={users} date={date} />}
            {section === 'workspaces' && <WorkspacesTable identity={identity} workspaces={workspaces} date={date} />}
            {section === 'reports' && activityReport && <ActivityReportPanel report={activityReport} />}
            {section === 'billing' && llmUsage && <LLMUsagePanel usage={llmUsage} meteredUsage={usage} invoices={invoices} workspaces={workspaces} />}
            {section === 'audit' && <AuditTable events={audit} users={users} date={date} />}
          </>}
        </section>
      </div>
    </main>
  </div>
}

function ActivityReportPanel({ report }: { report: AdminActivityReport }) {
  const { locale, t } = useI18n()
  const number = (value: number) => new Intl.NumberFormat(locale).format(value)
  const money = (value: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value / 1_000_000_000_000)
  const period = `${new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(report.periodStart))} - ${new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(report.periodEnd))}`
  const downloadCsv = () => {
    const columns = ['workspace', 'workflows_created', 'workflows_ready', 'workflows_in_progress', 'n8n_publications', 'agent_deliveries', 'agent_runs', 'input_tokens', 'output_tokens', 'total_tokens', 'estimated_cost_usd']
    const rows = report.workspaces.map((item) => [item.workspaceName, item.workflowsCreated, item.workflowsReady, item.workflowsInProgress, item.n8nPublications, item.agentDeliveries, item.agentRuns, item.inputTokens, item.outputTokens, item.totalTokens, item.estimatedCostPicousd / 1_000_000_000_000])
    const csv = [columns, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url; link.download = `activity-report-${report.periodStart.slice(0, 10)}.csv`; link.click()
    URL.revokeObjectURL(url)
  }
  return <>
    <div className="admin-section-heading admin-section-heading--actions"><div><span className="section-label">{t('adminReports')}</span><h2>{t('adminActivityReport')}</h2><p>{period}</p></div><button className="button button--secondary" onClick={downloadCsv}><Download size={16} />{t('adminDownloadCsv')}</button></div>
    <div className="admin-metrics">
      <div className="admin-metric"><span><FolderKanban size={18} /></span><small>{t('adminWorkflowsCreated')}</small><strong>{number(report.summary.workflowsCreated)}</strong><p>{t('adminReady')}: {number(report.summary.workflowsReady)}</p></div>
      <div className="admin-metric"><span><Activity size={18} /></span><small>{t('adminInProgress')}</small><strong>{number(report.summary.workflowsInProgress)}</strong><p>{t('adminCurrentState')}</p></div>
      <div className="admin-metric"><span><ServerCog size={18} /></span><small>{t('adminTransferred')}</small><strong>{number(report.summary.n8nPublications + report.summary.agentDeliveries)}</strong><p>n8n: {number(report.summary.n8nPublications)} · {t('adminAgents')}: {number(report.summary.agentDeliveries)}</p></div>
      <div className="admin-metric"><span><Coins size={18} /></span><small>{t('adminTokensSpent')}</small><strong>{number(report.summary.totalTokens)}</strong><p>{money(report.summary.estimatedCostPicousd)}</p></div>
    </div>
    <div className="admin-subheading"><h3>{t('adminWorkspaceBreakdown')}</h3><span>{report.workspaces.length}</span></div>
    <div className="admin-table admin-table--activity"><div className="admin-table__head"><span>{t('adminWorkspaces')}</span><span>{t('adminCreated')}</span><span>{t('adminReady')}</span><span>{t('adminInProgress')}</span><span>n8n</span><span>{t('adminAgents')}</span><span>{t('adminAgentRuns')}</span><span>{t('adminTokensSpent')}</span></div>{report.workspaces.map((item) => <div className="admin-table__row" key={item.workspaceId}><span><strong>{item.workspaceName}</strong></span><span>{number(item.workflowsCreated)}</span><span>{number(item.workflowsReady)}</span><span>{number(item.workflowsInProgress)}</span><span>{number(item.n8nPublications)}</span><span>{number(item.agentDeliveries)}</span><span>{number(item.agentRuns)}</span><span>{number(item.totalTokens)}<small>{money(item.estimatedCostPicousd)}</small></span></div>)}</div>
  </>
}

function LLMUsagePanel({ usage, meteredUsage, invoices, workspaces }: { usage: AdminLLMUsage; meteredUsage: AdminUsage | null; invoices: AdminInvoices | null; workspaces: AdminWorkspace[] }) {
  const { locale, t } = useI18n()
  const workspaceNames = new Map(workspaces.map((item) => [item.id, item.name]))
  const number = (value: number) => new Intl.NumberFormat(locale).format(value)
  const money = (value: string | number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(Number(value))
  const percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(usage.summary.budgetRatio)
  const statusLabel = t(`adminBudget_${usage.summary.status}`)
  const invoiceMoney = (minor: number | null, currency: string) => {
    if (minor === null) return t('adminNotPriced')
    const formatter = new Intl.NumberFormat(locale, { style: 'currency', currency })
    const digits = formatter.resolvedOptions().maximumFractionDigits ?? 2
    return formatter.format(minor / (10 ** digits))
  }
  return <>
    <div className="admin-section-heading"><span className="section-label">{t('adminAiCosts')}</span><h2>{t('adminLlmUsage')}</h2></div>
    {usage.alerts.map((alert) => <div className={`notice ${alert.severity === 'critical' ? 'notice--error' : 'notice--warning'}`} key={alert.code}><AlertTriangle size={17} /><span>{t(`adminAlert_${alert.code}`)}</span></div>)}
    <div className="admin-metrics">
      <div className="admin-metric"><span><CircleDollarSign size={18} /></span><small>{t('adminEstimatedCost')}</small><strong>{money(usage.summary.estimatedCostUsd)}</strong><p>{t('adminCurrentMonth')}</p></div>
      <div className="admin-metric"><span><Activity size={18} /></span><small>{t('adminInputTokens')}</small><strong>{number(usage.summary.inputTokens)}</strong><p>{t('adminOutputTokens')}: {number(usage.summary.outputTokens)}</p></div>
      <div className="admin-metric"><span><Coins size={18} /></span><small>{t('adminLlmBudget')}</small><strong>{Number(usage.summary.budgetUsd) > 0 ? money(usage.summary.budgetUsd) : '—'}</strong><p>{statusLabel}{Number(usage.summary.budgetUsd) > 0 ? ` · ${percent}` : ''}</p></div>
      <div className="admin-metric"><span><AlertTriangle size={18} /></span><small>{t('adminUnpricedUsage')}</small><strong>{number(usage.summary.unpricedRecords)}</strong><p>{t('adminUnpricedHint')}</p></div>
    </div>
    <div className="admin-subheading"><h3>{t('adminCostBreakdown')}</h3><span>{usage.breakdown.length}</span></div>
    <div className="admin-table admin-table--llm"><div className="admin-table__head"><span>{t('adminWorkspaces')}</span><span>{t('adminRequests')}</span><span>{t('adminInputTokens')}</span><span>{t('adminOutputTokens')}</span><span>{t('adminEstimatedCost')}</span></div>{usage.breakdown.map((item) => <div className="admin-table__row" key={`${item.workspaceId}:${item.provider}:${item.model}`}><span><strong>{workspaceNames.get(item.workspaceId) ?? item.workspaceId.slice(0, 8)}</strong></span><span>{number(item.requestCount)}</span><span>{number(item.inputTokens)}</span><span>{number(item.outputTokens)}</span><span>{item.estimatedCostPicousd === null ? t('adminNotPriced') : money(item.estimatedCostPicousd / 1_000_000_000_000)}</span></div>)}</div>
    {meteredUsage && <><div className="admin-subheading"><h3>{t('adminUsageLimits')}</h3><span>{meteredUsage.items.length}</span></div>{meteredUsage.alerts.map((alert) => <div className={`notice ${alert.severity === 'critical' ? 'notice--error' : 'notice--warning'}`} key={`${alert.workspaceId}:${alert.metric}`}><AlertTriangle size={17} /><span>{t(`adminAlert_${alert.code}`)} {workspaceNames.get(alert.workspaceId) ?? alert.workspaceId.slice(0, 8)} · {t(`adminUsage_${alert.metric}`)}: {number(alert.used)} / {number(alert.limit)}</span></div>)}<div className="admin-table admin-table--usage"><div className="admin-table__head"><span>{t('adminWorkspaces')}</span><span>{t('adminUsageMetric')}</span><span>{t('adminConsumed')}</span><span>{t('adminReserved')}</span><span>{t('adminRemaining')}</span></div>{meteredUsage.items.map((item) => <div className="admin-table__row" key={`${item.workspaceId}:${item.metric}`}><span><strong>{workspaceNames.get(item.workspaceId) ?? item.workspaceId.slice(0, 8)}</strong></span><span>{t(`adminUsage_${item.metric}`)}</span><span>{number(item.consumed)}</span><span>{number(item.reserved)}</span><span>{item.remaining === null ? t('adminUnlimited') : number(item.remaining)}</span></div>)}</div></>}
    {invoices && <><div className="admin-subheading"><h3>{t('adminInvoices')}</h3><span>{invoices.total}</span></div>{invoices.alerts.map((alert) => <div className={`notice ${alert.severity === 'critical' ? 'notice--error' : 'notice--warning'}`} key={`${alert.invoiceId}:${alert.code}`}><AlertTriangle size={17} /><span>{t(`adminAlert_${alert.code}`)} {alert.workspaceId ? workspaceNames.get(alert.workspaceId) ?? alert.workspaceId.slice(0, 8) : t('adminInvoiceUnmapped')}</span></div>)}<div className="admin-table admin-table--invoices"><div className="admin-table__head"><span>{t('adminWorkspaces')}</span><span>{t('adminInvoice')}</span><span>{t('status')}</span><span>{t('adminProviderAmount')}</span><span>{t('adminExpectedAmount')}</span><span>{t('adminReconciliation')}</span></div>{invoices.items.map((item) => <div className="admin-table__row" key={item.id}><span><strong>{item.workspaceId ? workspaceNames.get(item.workspaceId) ?? item.workspaceId.slice(0, 8) : t('adminInvoiceUnmapped')}</strong></span><span><code>{item.externalInvoiceId}</code></span><span>{t(`adminInvoiceStatus_${item.providerStatus}`)}</span><span>{invoiceMoney(item.providerAmountDueMinor, item.currency)}</span><span>{invoiceMoney(item.reconciliation?.expectedAmountMinor ?? null, item.currency)}</span><span><StatusBadge active={item.reconciliation?.status === 'matched'} label={t(`adminReconciliation_${item.reconciliation?.status ?? 'unmapped'}`)} /></span></div>)}</div></>}
  </>
}

function AdminOverview({ identity, users, workspaces, audit, projectCount, activeUsers, date }: { identity: AdminIdentity; users: AdminUser[]; workspaces: AdminWorkspace[]; audit: AdminAuditEvent[]; projectCount: number; activeUsers: number; date: (value: string) => string }) {
  const { t } = useI18n()
  const metrics = [
    { icon: Users, label: t('adminTotalUsers'), value: users.length, detail: `${t('adminActiveAccounts')}: ${activeUsers}` },
    { icon: Building2, label: t('adminTotalWorkspaces'), value: workspaces.length, detail: `${t('projects')}: ${projectCount}` },
    { icon: Activity, label: t('adminAudit'), value: audit.length, detail: t('adminRecentEvents') },
    { icon: identity.capabilities.billingEnabled ? CircleDollarSign : ShieldCheck, label: t('adminMode'), value: identity.capabilities.mode === 'hosted' ? t('adminHosted') : t('adminSelfHosted'), detail: identity.capabilities.billingEnabled ? t('adminBillingOn') : t('adminBillingOff') },
  ]
  return <>
    <div className="admin-section-heading"><span className="section-label">{t('adminOverview')}</span><h2>{t('serviceStatus')}</h2></div>
    <div className="admin-metrics">{metrics.map(({ icon: Icon, label, value, detail }) => <div className="admin-metric" key={label}><span><Icon size={18} /></span><small>{label}</small><strong>{value}</strong><p>{detail}</p></div>)}</div>
    <div className="admin-split">
      <div><div className="admin-subheading"><h3>{t('adminRecentWorkspaces')}</h3><span>{workspaces.length}</span></div><div className="admin-compact-list">{workspaces.slice(0, 5).map((item) => <div key={item.id}><span className="admin-list-icon"><Building2 size={16} /></span><span><strong>{item.name}</strong><small>{t('projects')}: {item.projectCount} · {t('adminMembers')}: {item.memberCount}</small></span><time>{date(item.createdAt)}</time></div>)}</div></div>
      <div><div className="admin-subheading"><h3>{t('adminRecentEvents')}</h3><span>{audit.length}</span></div><div className="admin-compact-list">{audit.slice(0, 5).map((item) => <div key={item.id}><span className="admin-list-icon"><ClipboardList size={16} /></span><span><strong>{adminActionLabel(item.action, t)}</strong><small>{item.reason}</small></span><time>{date(item.createdAt)}</time></div>)}</div></div>
    </div>
  </>
}

function UsersTable({ users, date }: { users: AdminUser[]; date: (value: string) => string }) {
  const { t } = useI18n()
  return <><div className="admin-section-heading"><span className="section-label">{t('adminUsers')}</span><h2>{t('adminUserAccess')}</h2></div><div className="admin-table admin-table--users"><div className="admin-table__head"><span>{t('email')}</span><span>{t('serviceRole')}</span><span>{t('status')}</span><span>{t('adminWorkspaces')}</span><span>{t('updated')}</span></div>{users.map((item) => <div className="admin-table__row" key={item.id}><span className="admin-person"><i>{item.email.slice(0, 1).toUpperCase()}</i><strong>{item.email}</strong></span><span><RoleBadge role={item.serviceRole} /></span><span><StatusBadge active={item.isActive} /></span><span>{item.workspaceCount}</span><time>{date(item.createdAt)}</time></div>)}</div></>
}

function WorkspacesTable({ identity, workspaces, date }: { identity: AdminIdentity; workspaces: AdminWorkspace[]; date: (value: string) => string }) {
  const { t } = useI18n()
  return <><div className="admin-section-heading"><span className="section-label">{t('adminWorkspaces')}</span><h2>{identity.capabilities.mode === 'hosted' ? t('adminCommercialState') : t('adminLocalState')}</h2></div><div className="admin-table admin-table--workspaces"><div className="admin-table__head"><span>{t('name')}</span><span>{t('adminMembers')}</span><span>{t('projects')}</span><span>{t('adminPlan')}</span><span>{identity.capabilities.mode === 'hosted' ? t('status') : t('adminLicense')}</span><span>{t('updated')}</span></div>{workspaces.map((item) => <div className="admin-table__row" key={item.id}><span><strong>{item.name}</strong><small>{item.defaultLocale.toUpperCase()}</small></span><span>{item.memberCount}</span><span>{item.projectCount}</span><span><code>{item.commercialState?.planId ?? '—'}</code></span><span>{identity.capabilities.mode === 'hosted' ? <StatusBadge label={item.commercialState?.status ?? '—'} active={item.commercialState?.status === 'active'} /> : item.license ? <StatusBadge label={t('adminLicenseActive')} active /> : <span className="muted">{t('adminNoLicense')}</span>}</span><time>{date(item.createdAt)}</time></div>)}</div></>
}

function AuditTable({ events, users, date }: { events: AdminAuditEvent[]; users: AdminUser[]; date: (value: string) => string }) {
  const { t } = useI18n()
  const emails = new Map(users.map((item) => [item.id, item.email]))
  return <><div className="admin-section-heading"><span className="section-label">{t('adminAudit')}</span><h2>{t('adminChangeHistory')}</h2></div><div className="admin-table admin-table--audit"><div className="admin-table__head"><span>{t('adminAction')}</span><span>{t('adminActor')}</span><span>{t('adminTarget')}</span><span>{t('adminReason')}</span><span>{t('updated')}</span></div>{events.map((item) => <div className="admin-table__row" key={item.id}><span><strong>{adminActionLabel(item.action, t)}</strong></span><span>{emails.get(item.actorUserId) ?? item.actorUserId.slice(0, 8)}</span><span><code>{item.targetType}</code></span><span>{item.reason}</span><time>{date(item.createdAt)}</time></div>)}</div></>
}

function adminActionLabel(action: string, t: (key: 'adminActionUserAccessUpdated' | 'adminActionWorkspaceUpdated' | 'adminActionGeneric') => string) {
  if (action === 'user.access_updated') return t('adminActionUserAccessUpdated')
  if (action.startsWith('workspace.')) return t('adminActionWorkspaceUpdated')
  return t('adminActionGeneric')
}

function RoleBadge({ role }: { role: AdminUser['serviceRole'] }) { const { t } = useI18n(); return <span className={`role-badge role-badge--${role}`}>{t(`adminRole_${role}`)}</span> }
function StatusBadge({ active, label }: { active: boolean; label?: string }) { const { t } = useI18n(); return <span className={`status-badge ${active ? 'is-active' : 'is-inactive'}`}>{label ?? (active ? t('adminActive') : t('adminBlocked'))}</span> }
