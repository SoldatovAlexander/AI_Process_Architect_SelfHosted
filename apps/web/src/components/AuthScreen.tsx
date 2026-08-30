import { useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { ApiError, authenticate } from '../api'
import { useI18n } from '../i18n/context'
import { Brand } from './Brand'
import { LanguageSwitch } from './LanguageSwitch'

export function AuthScreen({ onAuthenticated }: { onAuthenticated: (mode: 'login' | 'register') => Promise<void> }) {
  const { locale, t } = useI18n()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await authenticate(mode, email, password, locale)
      await onAuthenticated(mode)
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : t('error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-page__header"><Brand /><LanguageSwitch /></header>
      <section className="auth-panel">
        <div className="auth-panel__context">
          <span className="context-index">01</span>
          <h1>{t('tagline')}</h1>
          <p className="auth-panel__formats">Process IR · BPMN 2.0 · n8n · Agent-ready</p>
          <span className="auth-panel__separator" aria-hidden="true" />
          <p className="auth-panel__outcome">{t('authOutcome')}</p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-form__heading">
            <span className="section-label">{mode === 'login' ? t('login') : t('register')}</span>
            <h2>{mode === 'login' ? t('loginTitle') : t('registerTitle')}</h2>
          </div>
          <label>{t('email')}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
          <label>{t('password')}
            <span className="password-field">
              <input type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 10 : 1} required />
              <button type="button" className="icon-button" onClick={() => setVisible(!visible)} title={visible ? t('hidePassword') : t('showPassword')}>{visible ? <EyeOff size={17} /> : <Eye size={17} />}</button>
            </span>
            {mode === 'register' && <small>{t('passwordHint')}</small>}
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button--primary button--wide" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={18} /> : <>{mode === 'login' ? t('login') : t('register')}<ArrowRight size={18} /></>}
          </button>
          <p className="auth-form__switch">
            {mode === 'login' ? t('noAccount') : t('hasAccount')}{' '}
            <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
              {mode === 'login' ? t('register') : t('login')}
            </button>
          </p>
        </form>
      </section>
      <footer className="auth-page__footer"><span>{t('authWorkspace')}</span><span>Process IR 0.2</span></footer>
    </main>
  )
}
