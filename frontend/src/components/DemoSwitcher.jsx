import { useState } from 'react'
import { supabase } from '../services/supabase.js'

const DEMO_ROLES = [
  {
    key: 'student',
    label: 'Student',
    path: '/student/dashboard',
    email: import.meta.env.VITE_DEMO_STUDENT_EMAIL || '',
    password: import.meta.env.VITE_DEMO_STUDENT_PASSWORD || '',
  },
  {
    key: 'warden',
    label: 'Warden',
    path: '/warden/dashboard',
    email: import.meta.env.VITE_DEMO_WARDEN_EMAIL || '',
    password: import.meta.env.VITE_DEMO_WARDEN_PASSWORD || '',
  },
  {
    key: 'worker',
    label: 'Worker',
    path: '/worker/dashboard',
    email: import.meta.env.VITE_DEMO_WORKER_EMAIL || '',
    password: import.meta.env.VITE_DEMO_WORKER_PASSWORD || '',
  },
]

export default function DemoSwitcher({ currentEmail }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  if (!currentEmail) return null
  const normalized = currentEmail.trim().toLowerCase()
  const isDemo = DEMO_ROLES.some(r => r.email.trim().toLowerCase() === normalized)
  if (!isDemo) return null

  async function switchTo(targetKey) {
    setBusy(true); setError('')
    const target = DEMO_ROLES.find(r => r.key === targetKey)
    if (!target) return
    try {
      await supabase.auth.signOut()
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: target.email,
        password: target.password,
      })
      if (signInError) throw signInError
      window.location.replace(target.path)
    } catch (err) {
      setError(err.message || 'Could not switch role.')
    } finally {
      setBusy(false)
      setIsOpen(false)
    }
  }

  const others = DEMO_ROLES.filter(r => r.email.trim().toLowerCase() !== normalized)

  return (
    <div className="demo-switcher" role="region" aria-label="Switch demo role">
      <button
        type="button"
        className="demo-switcher__toggle"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
      >
        Switch role
      </button>
      {isOpen && (
        <div className="demo-switcher__panel">
          <p className="demo-switcher__note">Demo account: {currentEmail}</p>
          {others.map(r => (
            <button
              key={r.key}
              type="button"
              className={`demo-switcher__role${busy ? ' disabled' : ''}`}
              disabled={busy}
              onClick={() => switchTo(r.key)}
            >
              {busy ? 'Switching…' : `Try as ${r.label}`}
            </button>
          ))}
          {error && <p className="demo-switcher__error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  )
}
