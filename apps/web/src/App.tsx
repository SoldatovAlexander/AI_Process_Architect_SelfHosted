import { useEffect, useState } from 'react'
import { api, clearTokens, hasSession } from './api'
import type { AdminIdentity, User } from './types'
import { AuthScreen } from './components/AuthScreen'
import { ProjectsScreen } from './components/ProjectsScreen'
import { WorkspaceScreen } from './components/WorkspaceScreen'
import { AdminScreen } from './components/AdminScreen'
import { HelpProvider } from './components/HelpMode'

type Route = { screen: 'projects' } | { screen: 'workspace'; projectId: string } | { screen: 'admin' }

function routeFromLocation(): Route {
  if (window.location.pathname === '/admin') return { screen: 'admin' }
  const match = window.location.pathname.match(/^\/projects\/([^/]+)$/)
  return match ? { screen: 'workspace', projectId: match[1] } : { screen: 'projects' }
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [admin, setAdmin] = useState<AdminIdentity | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [route, setRoute] = useState<Route>(routeFromLocation)
  const [invitationNotice, setInvitationNotice] = useState<'accepted' | 'error' | null>(null)

  async function loadUser() {
    try {
      const nextUser = await api.me()
      setUser(nextUser)
      setAdmin(await api.adminMe().catch(() => null))
    } catch {
      clearTokens()
      setUser(null)
      setAdmin(null)
    } finally {
      setInitializing(false)
    }
  }

  async function handleAuthenticated(mode: 'login' | 'register') {
    if (mode === 'register') {
      const invitation = new URLSearchParams(window.location.search).get('workspace_invitation')
      window.history.replaceState({}, '', invitation ? `/?workspace_invitation=${encodeURIComponent(invitation)}` : '/')
      setRoute({ screen: 'projects' })
    }
    await loadUser()
  }

  useEffect(() => {
    if (hasSession()) loadUser()
    else setInitializing(false)
    const popState = () => setRoute(routeFromLocation())
    window.addEventListener('popstate', popState)
    return () => window.removeEventListener('popstate', popState)
  }, [])

  useEffect(() => {
    if (!initializing && user && route.screen === 'admin' && !admin) {
      window.history.replaceState({}, '', '/')
      setRoute({ screen: 'projects' })
    }
  }, [admin, initializing, route, user])

  useEffect(() => {
    if (!user) return
    const params = new URLSearchParams(window.location.search)
    const token = params.get('workspace_invitation')
    if (!token) return
    params.delete('workspace_invitation')
    window.history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
    api.acceptWorkspaceInvitation(token)
      .then(async () => { setInvitationNotice('accepted'); setUser(await api.me()) })
      .catch(() => setInvitationNotice('error'))
  }, [user])

  function navigate(next: Route) {
    const path = next.screen === 'workspace' ? `/projects/${next.projectId}` : next.screen === 'admin' ? '/admin' : '/'
    window.history.pushState({}, '', path)
    setRoute(next)
  }

  if (initializing) return <div className="full-loading">AI Process Architect</div>
  if (!user) return <AuthScreen onAuthenticated={handleAuthenticated} />
  const screen = route.screen === 'workspace'
    ? <WorkspaceScreen projectId={route.projectId} onBack={() => navigate({ screen: 'projects' })} />
    : route.screen === 'admin' && admin
      ? <AdminScreen identity={admin} onBack={() => navigate({ screen: 'projects' })} onLogout={async () => { await api.logout(); setUser(null); setAdmin(null); navigate({ screen: 'projects' }) }} />
      : <ProjectsScreen user={user} invitationNotice={invitationNotice} onAdmin={admin ? () => navigate({ screen: 'admin' }) : undefined} onOpen={(projectId) => navigate({ screen: 'workspace', projectId })} onLogout={async () => { await api.logout(); setUser(null); setAdmin(null); navigate({ screen: 'projects' }) }} />
  return <HelpProvider>{screen}</HelpProvider>
}
