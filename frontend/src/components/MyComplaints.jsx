import { useCallback, useEffect, useRef, useState } from 'react'
import {
  confirmComplaint,
  fetchComplaint,
  fetchMyComplaints,
  reopenComplaint,
} from '../services/complaints.js'

const POLL_INTERVAL_MS = 10_000

const human = value => (value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : 'Unclassified')
const when = value => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')

function StatusBadge({ status }) {
  const kind = status === 'COMPLETED' ? 'done' : status === 'WARDEN_REVIEW' || status === 'SUBMITTED' ? 'wait' : 'active'
  return <span className={`track-badge track-badge--${kind}`}>{human(status)}</span>
}

function Detail({ id, accessToken, onClose }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [reason, setReason] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchComplaint(id, accessToken)
      .then(data => { if (!cancelled) setDetail(data) })
      .catch(err => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [id, accessToken])

  async function act(action) {
    setBusy(true); setError(''); setMessage('')
    try {
      const updated = action === 'confirm'
        ? await confirmComplaint(id, accessToken)
        : await reopenComplaint(id, reason.trim(), accessToken)
      setDetail(updated)
      setMessage(action === 'confirm'
        ? 'Marked as resolved. Thank you for confirming.'
        : 'Reopened. The warden will review your complaint again.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="track-detail"><p className="track-error" role="alert">{error}</p><button type="button" className="track-back" onClick={onClose}>Back</button></div>
  if (!detail) return <p className="track-loading" role="status">Loading complaint details…</p>

  const isCompleted = detail.status === 'COMPLETED'
  const confirmed = (detail.history ?? []).some(entry => entry.note === 'Student confirmed resolved')

  return (
    <div className="track-detail">
      <button type="button" className="track-back" onClick={onClose}>Back to my complaints</button>
      <p className="track-reference">Complaint #{detail.id} · {human(detail.category)} · Block {detail.block} / Room {detail.room}</p>
      <p className="track-description">{detail.description}</p>
      {detail.warden_note ? <p className="track-note"><strong>Warden note:</strong> {detail.warden_note}</p> : null}
      {detail.worker_note ? <p className="track-note"><strong>Worker note:</strong> {detail.worker_note}</p> : null}
      {detail.approved_worker ? <p className="track-note"><strong>Assigned to:</strong> {detail.approved_worker.name}</p> : null}

      <h4 className="track-timeline-title">Status timeline</h4>
      <ol className="track-timeline">
        {(detail.history ?? []).map((entry, index) => (
          <li key={entry.created_at + ':' + index}>
            <StatusBadge status={entry.new_status} />
            <span className="track-timeline-meta">{when(entry.created_at)}{entry.note ? ` — ${entry.note}` : ''}</span>
          </li>
        ))}
      </ol>

      {isCompleted && !confirmed ? (
        <div className="track-actions">
          <p className="track-actions-help">Was your problem actually fixed?</p>
          <button type="button" className="button button--secondary" disabled={busy} onClick={() => act('confirm')}>
            Yes, fixed
          </button>
          <div className="track-reopen">
            <textarea
              className="track-reason"
              rows={2}
              minLength={5}
              maxLength={300}
              placeholder="What is still not fixed? (5-300 characters)"
              value={reason}
              onChange={event => setReason(event.target.value)}
            />
            <button
              type="button"
              className="button button--secondary"
              disabled={busy || reason.trim().length < 5}
              onClick={() => act('reopen')}
            >
              Not fixed
            </button>
          </div>
        </div>
      ) : null}
      {isCompleted && confirmed ? <p className="track-note">You confirmed this complaint as resolved.</p> : null}
      {message ? <p className="track-message" role="status">{message}</p> : null}
      {busy ? <p className="track-loading" role="status">Working…</p> : null}
    </div>
  )
}

function Row({ item, onOpen }) {
  return (
    <li className="track-row">
      <button type="button" className="track-row__button" onClick={onOpen}>
        <span className="track-row__head">
          <span className="track-row__identity"><strong>Complaint #{item.id}</strong><small>{human(item.category)}</small></span>
          <StatusBadge status={item.status} />
        </span>
        <span className="track-row__meta">
          <span>Block {item.block} · Room {item.room}</span><span>{human(item.severity)} priority</span><time dateTime={item.created_at}>{when(item.created_at)}</time>
        </span>
        <span className="track-row__desc">{item.description}</span>
        <span className="track-row__action">View progress <span aria-hidden="true">→</span></span>
      </button>
    </li>
  )
}

export default function MyComplaints({ accessToken }) {
  const [state, setState] = useState({ loading: true, error: '', items: [], openId: null })
  const itemsRef = useRef([])
  const pollRef = useRef(null)
  const listRef = useRef(fetchMyComplaints)

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setState(s => ({ ...s, loading: true, error: '' }))
    try {
      const items = await listRef.current(accessToken)
      itemsRef.current = items
      setState(s => ({ ...s, loading: false, error: '', items }))
      return items
    } catch (error) {
      setState(s => ({ ...s, loading: false, error: error.message }))
      return null
    }
  }, [accessToken])

  useEffect(() => { load() }, [load])

  // Poll every 10s only while at least one complaint is not COMPLETED; the
  // fetch is skipped while the tab is hidden, and polling stops once
  // everything is completed (cleared on unmount).
  useEffect(() => {
    function schedule() {
      pollRef.current = window.setTimeout(async () => {
        const items = itemsRef.current
        if (items.length && items.every(item => item.status === 'COMPLETED')) return
        if (document.visibilityState === 'visible') {
          await load({ quiet: true })
        }
        schedule()
      }, POLL_INTERVAL_MS)
    }
    schedule()
    return () => window.clearTimeout(pollRef.current)
  }, [load])

  if (state.loading) return <div className="track-state" role="status"><span className="track-state__icon" aria-hidden="true">…</span><strong>Loading your reports</strong><span>Getting the latest updates from your hostel team.</span></div>
  if (state.error) return <div className="track-state track-state--error" role="alert"><span className="track-state__icon" aria-hidden="true">!</span><strong>We couldn’t load your reports</strong><span>{state.error}</span><button type="button" className="track-retry" onClick={() => load()}>Try again</button></div>
  if (!state.items.length) {
    return (
      <div className="track-state track-empty">
        <span className="track-state__icon" aria-hidden="true">＋</span>
        <strong>No reports yet</strong>
        <span>When you report a hostel issue, its progress will appear here.</span>
        <p className="track-empty__help">Choose the <strong>Report a problem</strong> tab to get started.</p>
      </div>
    )
  }

  const open = state.items.find(item => item.id === state.openId)
  const activeCount = state.items.filter(item => item.status !== 'COMPLETED').length
  const resolvedCount = state.items.length - activeCount

  return (
    <div className="track">
      {open ? (
        <Detail id={open.id} accessToken={accessToken} onClose={() => setState(s => ({ ...s, openId: null }))} />
      ) : (
        <>
          <header className="track-overview">
            <div><p className="track-overview__eyebrow">YOUR REQUESTS</p><h3>Complaint tracking</h3><p>Follow updates and confirm when an issue is resolved.</p></div>
            <div className="track-summary" aria-label={`${state.items.length} total complaints, ${activeCount} active, ${resolvedCount} resolved`}>
              <span><strong>{state.items.length}</strong><small>Total</small></span>
              <span><strong>{activeCount}</strong><small>In progress</small></span>
              <span><strong>{resolvedCount}</strong><small>Resolved</small></span>
            </div>
          </header>
          <ul className="track-list">
            {state.items.map(item => (
              <Row key={item.id} item={item} onOpen={() => setState(s => ({ ...s, openId: item.id }))} />
            ))}
          </ul>
          <p className="track-refresh"><span className="track-live-dot" aria-hidden="true" />Updates automatically every few seconds while a report is active.</p>
        </>
      )}
    </div>
  )
}
