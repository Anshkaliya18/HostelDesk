import { cloneElement, useEffect, useState } from 'react'
import { supabase } from '../services/supabase.js'
import { getRoleProfile, signupStudent, signupWarden, signupWorker } from '../services/roleApi.js'
import './role-app.css'

const roles = {
  student: { label: 'Student', portal: 'STUDENT PORTAL', headline: 'A better way to get hostel issues sorted.', copy: 'Report a problem, follow its progress, and get back to your day.' },
  warden: { label: 'Warden', portal: 'WARDEN PORTAL', headline: 'Keep hostel operations moving.', copy: 'Review reports, assign work, and see what needs attention.' },
  worker: { label: 'Worker', portal: 'WORKER PORTAL', headline: 'Your assigned work, all in one place.', copy: 'See the details, update progress, and close the loop.' },
}
const dashboardPath = role => `/${role}/dashboard`

function AuthScreen({ role, mode, setMode, session, onSignOut, formError, setFormError }) {
  const config = roles[role]
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [workerType, setWorkerType] = useState('CLEANER')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const isSignup = mode === 'signup'

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setFormError(''); setMessage('')
    try {
      if (!supabase) throw new Error('Supabase Auth is not configured for this app.')
      const normalizedEmail = email.trim().toLowerCase()
      if (isSignup) {
        const payload = { name: name.trim(), email: normalizedEmail, password }
        if (role === 'worker') payload.worker_type = workerType
        const signup = { student: signupStudent, warden: signupWarden, worker: signupWorker }[role]
        await signup(payload)
        const { error } = await supabase.auth.signInWithPassword({ email: normalizedEmail, password })
        if (error) throw new Error('Your account was created, but sign-in did not finish. Sign in with the same email and password.')
        setMessage('Account created. Opening your dashboard…')
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email: normalizedEmail, password })
        if (error) throw new Error('Email or password is incorrect.')
        setMessage('Signed in. Opening your dashboard…')
      }
    } catch (error) {
      setFormError(error.message || 'The request could not be completed.')
    } finally {
      setBusy(false)
    }
  }

  function changeMode(next) {
    setFormError('')
    setMessage('')
    setMode(next)
  }

  return <main className={`role-auth-shell role-auth-shell--${role}`}>
    <section className="role-auth-card">
      <aside className="role-auth-visual">
        <a href="/" className="role-auth-brand"><span className="role-brand-mark">H</span><span>HostelDesk<small>{config.portal}</small></span></a>
        <div className="role-auth-pitch">
          <span className="role-auth-eyebrow">A calmer hostel, one report at a time</span>
          <h2>{config.headline}</h2>
          <p>{config.copy}</p>
        </div>
        <div className="role-workflow" aria-label="Complaint workflow">
          <div><span className="workflow-icon">01</span><span><strong>Report</strong><small>Share the issue</small></span></div>
          <i aria-hidden="true" />
          <div><span className="workflow-icon">02</span><span><strong>Review</strong><small>Route it to the right person</small></span></div>
          <i aria-hidden="true" />
          <div><span className="workflow-icon">03</span><span><strong>Resolve</strong><small>Track progress to completion</small></span></div>
        </div>
        <p className="role-auth-visual-foot">One shared desk for students and hostel teams.</p>
      </aside>

      <div className="role-auth-content">
        <div className="role-auth-mobile-brand"><span className="role-brand-mark">H</span><span>HostelDesk</span></div>
        <div className="role-auth-role-picker" aria-label="Choose a portal">
          {Object.entries(roles).map(([key, value]) => <a key={key} href={`/${key}/login`} className={key === role ? 'active' : ''}>{value.label}</a>)}
        </div>
        <div className="role-auth-heading">
          <p className="role-auth-eyebrow">{config.portal}</p>
          <h1>{isSignup ? `Create your ${config.label.toLowerCase()} account` : `Welcome back`}</h1>
          <p>{isSignup ? 'A few details and you’re ready to go.' : `Sign in to continue to your ${config.label.toLowerCase()} workspace.`}</p>
        </div>

        <div className="role-auth-mode" role="tablist" aria-label="Account access">
          <button type="button" role="tab" aria-selected={!isSignup} className={!isSignup ? 'active' : ''} onClick={() => changeMode('login')}>Sign in</button>
          <button type="button" role="tab" aria-selected={isSignup} className={isSignup ? 'active' : ''} onClick={() => changeMode('signup')}>Create account</button>
        </div>

        <form className="role-auth-form" onSubmit={submit}>
          {isSignup && <label>Full name<input required minLength="2" maxLength="120" autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" /></label>}
          <label>Email address<input required type="email" maxLength="254" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" /></label>
          <label>Password<span className="role-password-wrap"><input required type={showPassword ? 'text' : 'password'} autoComplete={isSignup ? 'new-password' : 'current-password'} minLength={isSignup ? 8 : undefined} maxLength="128" value={password} onChange={e => setPassword(e.target.value)} placeholder={isSignup ? 'At least 8 characters' : 'Enter your password'} /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button></span></label>
          {isSignup && role === 'worker' && <label>Work type<select value={workerType} onChange={e => setWorkerType(e.target.value)}>{['ELECTRICIAN','PLUMBER','CLEANER','CARPENTER'].map(type => <option key={type} value={type}>{type[0] + type.slice(1).toLowerCase()}</option>)}</select></label>}
          {formError && <p className="role-auth-error" role="alert">{formError}</p>}
          {message && <p className="role-auth-message" role="status">{message}</p>}
          {!supabase && <p className="role-auth-error" role="alert">Authentication is not configured. Ask the app administrator to set up Supabase.</p>}
          <button className="role-auth-submit" disabled={busy || !supabase}>{busy ? <><span className="role-spinner" />Please wait…</> : isSignup ? 'Create account' : 'Sign in'}<span aria-hidden="true">→</span></button>
        </form>
        <p className="role-auth-security">Your account is protected by Supabase Auth. HostelDesk never stores your password.</p>
        {session && <button className="role-auth-signout" type="button" onClick={onSignOut}>Sign out of this account</button>}
      </div>
    </section>
  </main>
}

export function RoleGate({ role, dashboard }) {
  const [session, setSession] = useState(null)
  const [ready, setReady] = useState(!supabase)
  const [result, setResult] = useState({ token: null, profile: null, error: '' })
  const [formError, setFormError] = useState('')
  const path = window.location.pathname
  const [authMode, setAuthMode] = useState(path.endsWith('/signup') ? 'signup' : 'login')

  useEffect(() => {
    if (!supabase) return
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, value) => setSession(value))
    supabase.auth.getSession().then(({ data, error }) => { if (!error) setSession(data.session); setReady(true) })
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!ready || !session) return
    let active = true
    const token = session.access_token
    getRoleProfile(token)
      .then(profile => { if (active) setResult({ token, profile, error: '' }) })
      .catch(error => { if (active) setResult({ token, profile: null, error: error.message }) })
    return () => { active = false }
  }, [ready, session])

  if (!ready || (session && result.token !== session.access_token)) return <main className="role-auth-loading"><span className="role-spinner" />Restoring your secure session…</main>
  if (result.profile && session) {
    if (result.profile.role !== role.toUpperCase()) {
      const home = dashboardPath(result.profile.role.toLowerCase())
      window.location.replace(home)
      return <main className="role-auth-loading">Opening your {result.profile.role.toLowerCase()} workspace…</main>
    }
    if (path !== dashboardPath(role) && !path.startsWith(`/${role}/complaints`)) window.history.replaceState({}, '', dashboardPath(role))
    return cloneElement(dashboard, { session, profile: result.profile, onSignOut: () => supabase.auth.signOut() })
  }

  return <AuthScreen
    role={role}
    mode={authMode}
    session={session}
    onSignOut={() => supabase?.auth.signOut()}
    setMode={next => { setAuthMode(next); window.history.pushState({}, '', `/${role}/${next === 'signup' ? 'signup' : 'login'}`); setFormError('') }}
    formError={formError || result.error}
    setFormError={setFormError}
  />
}
