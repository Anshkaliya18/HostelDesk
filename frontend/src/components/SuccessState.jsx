import { useEffect, useRef } from 'react'
import { CheckIcon } from './Icons.jsx'

export default function SuccessState({ reference, status = null, isPreview = false, onReset, onTrack }) {
  const headingRef = useRef(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <section className="panel success-panel" aria-labelledby="success-title">
      <div className="success-panel__body">
        <span className="success-mark" aria-hidden="true">
          <CheckIcon size={21} />
        </span>

        <h2 className="success-title" id="success-title" ref={headingRef} tabIndex={-1}>
          Complaint submitted
        </h2>
        <p className="success-copy">
          Your complaint has been sent to the hostel team for review.
        </p>

        <div className="reference-box">
          <span className="reference-box__label">
            {isPreview ? 'Preview reference' : 'Complaint reference'}
          </span>
          <span className="reference-box__value">
            {reference ? `#${reference.replace(/^#/, '')}` : 'Pending'}
          </span>
        </div>

        {status ? (
          <p className="success-help">
            Status: {status}. The warden reviews it next; the AI suggestion is prepared in the
            background and never assigns a worker automatically.
          </p>
        ) : null}

        <p className="success-help">
          {reference
            ? 'Keep this reference for your records.'
            : 'The hostel office will assign a reference when your complaint is registered.'}
        </p>

        {reference && onTrack ? (
          <button type="button" className="button button--secondary" onClick={onTrack}>
            Track this complaint
          </button>
        ) : null}

        <button type="button" className="button button--secondary" onClick={onReset}>
          Submit another complaint
        </button>
      </div>
    </section>
  )
}
