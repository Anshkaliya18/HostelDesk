import { lazy, Suspense, useState } from 'react'
import Header from './components/Header.jsx'
import ComplaintForm from './components/ComplaintForm.jsx'
import SuccessState from './components/SuccessState.jsx'
import MyComplaints from './components/MyComplaints.jsx'
import ColdStartBanner from './components/ColdStartBanner.jsx'
import DemoSwitcher from './components/DemoSwitcher.jsx'
import { warmUp } from './utils/coldStart.js'
import { API_BASE_URL } from './services/apiBase.js'
import { RoleGate } from './pages/RoleApp.jsx'

const WardenApp = lazy(() => import('./pages/warden/WardenApp.jsx'))
const WorkerApp = lazy(() => import('./pages/worker/WorkerApp.jsx'))

function StudentDashboard({ session, profile, onSignOut }) {
  const [submission, setSubmission] = useState(null)
  const [hasPreviousSubmission, setHasPreviousSubmission] = useState(false)
  const [tab, setTab] = useState('report')
  const [walkthroughDismissed, setWalkthroughDismissed] = useState(
    sessionStorage.getItem('hosteldesk_walkthrough_dismissed') === 'true'
  )
  const demoStudentEmail = (import.meta.env.VITE_DEMO_STUDENT_EMAIL || '').trim().toLowerCase()
  const isDemoStudent = Boolean(
    session && profile && profile.email && demoStudentEmail && profile.email.trim().toLowerCase() === demoStudentEmail
  )

  function handleSubmission(result) {
    setSubmission(result)
    setHasPreviousSubmission(true)
  }

  function handleReset() {
    setSubmission(null)
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <Header profile={profile} onSignOut={onSignOut} />
      {isDemoStudent && <DemoSwitcher currentEmail={profile.email} />}

      <main className="main" id="main-content" tabIndex={-1}>
        <div className="container page-shell">
          <div className="page-grid">
            {isDemoStudent && !walkthroughDismissed && (
              <section className="demo-walkthrough" aria-label="Demo walkthrough">
                <button type="button" className="demo-walkthrough__dismiss" onClick={() => { setWalkthroughDismissed(true); sessionStorage.setItem('hosteldesk_walkthrough_dismissed', 'true') }} aria-label="Dismiss walkthrough">×</button>
                <h2>Demo walkthrough</h2>
                <ol>
                  <li>Report a problem with a photo — use "Report a problem" and submit.</li>
                  <li>Switch to Warden using "Switch role" and approve the AI suggestion.</li>
                  <li>Switch to Worker and complete the task with a note (5+ characters).</li>
                  <li>Switch back to Student and open "My complaints" to see Completed.</li>
                </ol>
              </section>
            )}
            <section className="intro" aria-labelledby="page-title">
              <p className="eyebrow">Hostel maintenance</p>
              <h1 className="intro__title" id="page-title">
                Report a hostel problem
              </h1>
              <p className="intro__copy">
                Tell us what needs attention. Add a photo if it helps us understand the
                issue.
              </p>

              <div className="student-tabs" role="tablist" aria-label="Student dashboard sections">
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'report'}
                  className={`student-tab${tab === 'report' ? ' student-tab--active' : ''}`}
                  onClick={() => setTab('report')}
                >
                  Report a problem
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === 'track'}
                  className={`student-tab${tab === 'track' ? ' student-tab--active' : ''}`}
                  onClick={() => setTab('track')}
                >
                  My complaints
                </button>
              </div>

              {!submission && tab === 'report' ? (
                <div className="intro__notes">
                  <h2 className="intro__notes-title">Before you submit</h2>
                  <ul className="intro__list">
                    <li>Include the block letter and room number.</li>
                    <li>Describe what is broken and how long it has been an issue.</li>
                    <li>Add a photo if it helps show the problem.</li>
                  </ul>
                  <p className="intro__process">
                    Reports are reviewed by the hostel office before maintenance work
                    is assigned. You can follow every step under "My complaints".
                  </p>
                </div>
              ) : null}
            </section>

            <div className="form-column">
              {tab === 'track' && !submission ? (
                <MyComplaints accessToken={session?.access_token} />
              ) : submission ? (
                <SuccessState
                  reference={submission.reference}
                  status={submission.status}
                  isPreview={submission.isPreview}
                  onReset={() => { handleReset(); setTab('report') }}
                  onTrack={() => { setSubmission(null); setTab('track') }}
                />
              ) : (
                <ComplaintForm
                  accessToken={session?.access_token}
                  onSuccess={handleSubmission}
                  autoFocusDescription={hasPreviousSubmission}
                />
              )}
            </div>
          </div>
        </div>
      </main>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <span>HostelDesk</span>
          <span>Student complaint desk</span>
        </div>
      </footer>
    </div>
  )
}

export default function App() {
  const path = window.location.pathname
  warmUp(API_BASE_URL)
  if (path.startsWith('/warden')) return <><ColdStartBanner /><Suspense fallback={<main className="role-auth-loading" role="status"><span className="role-spinner" />Loading Warden workspace…</main>}><WardenApp /></Suspense></>
  if (path.startsWith('/worker')) return <><ColdStartBanner /><Suspense fallback={<main className="role-auth-loading" role="status"><span className="role-spinner" />Loading Worker workspace…</main>}><WorkerApp /></Suspense></>
  return <><ColdStartBanner /><RoleGate role="student" dashboard={<StudentDashboard />} /></>
}
