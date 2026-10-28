import { lazy, Suspense, useState } from 'react'
import Header from './components/Header.jsx'
import ComplaintForm from './components/ComplaintForm.jsx'
import SuccessState from './components/SuccessState.jsx'
import MyComplaints from './components/MyComplaints.jsx'
import ColdStartBanner from './components/ColdStartBanner.jsx'
import { warmUp } from './utils/coldStart.js'
import { API_BASE_URL } from './services/apiBase.js'
import { RoleGate } from './pages/RoleApp.jsx'

const WardenApp = lazy(() => import('./pages/warden/WardenApp.jsx'))
const WorkerApp = lazy(() => import('./pages/worker/WorkerApp.jsx'))

function StudentDashboard({ session, profile, onSignOut }) {
  const [submission, setSubmission] = useState(null)
  const [hasPreviousSubmission, setHasPreviousSubmission] = useState(false)
  const [tab, setTab] = useState('report')

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

      <main className="main" id="main-content" tabIndex={-1}>
        <div className="container page-shell">
          <header className="page-heading">
            <p className="eyebrow">Hostel maintenance</p>
            <h1 className="page-heading__title" id="page-title">
              Report a hostel problem
            </h1>
            <p className="page-heading__copy">
              Tell us what needs attention in your block, attach a photo if it helps,
              and follow every update under &ldquo;My complaints&rdquo;.
            </p>
          </header>

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

          <div className={`dashboard-grid${submission ? ' dashboard-grid--single' : ''}`}>
            <div className="dashboard-main">
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

            {!submission ? (
              <aside className="dashboard-aside">
                {tab === 'report' ? (
                  <section className="aside-card" aria-labelledby="before-submit-title">
                    <h2 className="aside-card__title" id="before-submit-title">
                      Before you submit
                    </h2>
                    <ol className="checklist">
                      <li>
                        <span className="checklist__step" aria-hidden="true">1</span>
                        <span>Include the block letter and room number.</span>
                      </li>
                      <li>
                        <span className="checklist__step" aria-hidden="true">2</span>
                        <span>Describe what is broken and how long it has been an issue.</span>
                      </li>
                      <li>
                        <span className="checklist__step" aria-hidden="true">3</span>
                        <span>Add a photo if it helps show the problem.</span>
                      </li>
                    </ol>
                    <p className="aside-card__note">
                      Reports are reviewed by the hostel office before maintenance work
                      is assigned. You can follow every step under
                      &ldquo;My complaints&rdquo;.
                    </p>
                  </section>
                ) : (
                  <section className="aside-card" aria-labelledby="tracking-legend-title">
                    <h2 className="aside-card__title" id="tracking-legend-title">
                      Status guide
                    </h2>
                    <ul className="status-legend">
                      <li>
                        <span className="track-badge track-badge--wait">Submitted</span>
                        <span>Received by the hostel office and awaiting review.</span>
                      </li>
                      <li>
                        <span className="track-badge track-badge--active">In progress</span>
                        <span>Maintenance work is being arranged.</span>
                      </li>
                      <li>
                        <span className="track-badge track-badge--done">Completed</span>
                        <span>Confirm the fix from the complaint, or reopen it.</span>
                      </li>
                    </ul>
                    <p className="aside-card__note">
                      The list refreshes automatically every few seconds while a report
                      is active.
                    </p>
                  </section>
                )}
              </aside>
            ) : null}
          </div>
        </div>
      </main>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <span className="site-footer__brand">HostelDesk</span>
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
