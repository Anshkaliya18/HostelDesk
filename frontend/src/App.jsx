import { useState } from 'react'
import Header from './components/Header.jsx'
import ComplaintForm from './components/ComplaintForm.jsx'
import SuccessState from './components/SuccessState.jsx'

export default function App() {
  const [submission, setSubmission] = useState(null)
  const [hasPreviousSubmission, setHasPreviousSubmission] = useState(false)

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

      <Header />

      <main className="main" id="main-content" tabIndex={-1}>
        <div className="container page-shell">
          <div className="page-grid">
            <section className="intro" aria-labelledby="page-title">
              <p className="eyebrow">Hostel maintenance</p>
              <h1 className="intro__title" id="page-title">
                Report a hostel problem
              </h1>
              <p className="intro__copy">
                Tell us what needs attention. Add a photo if it helps us understand the
                issue.
              </p>

              {!submission ? (
                <div className="intro__notes">
                  <h2 className="intro__notes-title">Before you submit</h2>
                  <ul className="intro__list">
                    <li>Include the block letter and room number.</li>
                    <li>Describe what is broken and how long it has been an issue.</li>
                    <li>Add a photo if it helps show the problem.</li>
                  </ul>
                  <p className="intro__process">
                    Reports are reviewed by the hostel office before maintenance work
                    is assigned.
                  </p>
                </div>
              ) : null}
            </section>

            <div className="form-column">
              {submission ? (
                <SuccessState
                  reference={submission.reference}
                  isPreview={submission.isPreview}
                  onReset={handleReset}
                />
              ) : (
                <ComplaintForm
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
