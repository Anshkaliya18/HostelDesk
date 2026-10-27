import { useCallback, useEffect, useMemo, useState } from 'react'
import { LogoIcon } from '../../components/Icons.jsx'
import { RoleGate } from '../RoleApp.jsx'
import { getWorkerComplaint, getWorkerTasks, updateWorkerTask } from '../../services/roleApi.js'
import '../portal.css'

const human = value => value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : '—'
const date = value => value ? new Date(value).toLocaleString() : '—'

function WorkerMetric({ label, value, tone, helper }) {
  return <article className={`worker-metric worker-metric--${tone}`}>
    <span>{label}</span><strong>{value}</strong><small>{helper}</small>
  </article>
}

function TaskState({ status }) {
  const state = status === 'COMPLETED' ? 'done' : status === 'IN_PROGRESS' ? 'active' : 'waiting'
  return <span className={`worker-state-pill worker-state-pill--${state}`}>{human(status)}</span>
}

function TaskCard({ task, onOpen }) {
  return <article className="worker-task-card">
    <div className="worker-task-card__top">
      <div><span className="worker-task-card__ref">Complaint #{task.complaint_id}</span><h3>{human(task.category)}</h3></div>
      <TaskState status={task.status} />
    </div>
    <p className="worker-task-card__description">{task.description}</p>
    <div className="worker-task-card__meta">
      <span><small>Location</small><strong>Block {task.block} · Room {task.room}</strong></span>
      <span><small>Priority</small><strong className={`worker-priority worker-priority--${(task.severity || 'low').toLowerCase()}`}>{human(task.severity)}</strong></span>
      <span><small>Assigned</small><strong>{date(task.assigned_at || task.created_at)}</strong></span>
    </div>
    <button type="button" className="button button--secondary worker-task-open" onClick={onOpen}>View task <span aria-hidden="true">→</span></button>
  </article>
}

function WorkerWorkspace({ profile, onSignOut }) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(window.location.pathname.match(/^\/worker\/complaints\/(\d+)/)?.[1] || null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(() => Boolean(window.location.pathname.match(/^\/worker\/complaints\/(\d+)/)))
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('active')

  useEffect(() => {
    const handle = () => {
      const next = window.location.pathname.match(/^\/worker\/complaints\/(\d+)/)?.[1] || null
      setSelected(next)
      setDetail(null)
      setDetailLoading(Boolean(next))
      setError('')
    }
    window.addEventListener('popstate', handle)
    return () => window.removeEventListener('popstate', handle)
  }, [])

  function openComplaint(id) {
    window.history.pushState({}, '', `/worker/complaints/${id}`)
    setSelected(String(id))
    setDetail(null)
    setDetailLoading(true)
    setError('')
    window.scrollTo(0, 0)
  }

  function closeComplaint() {
    window.history.pushState({}, '', '/worker/dashboard')
    setSelected(null)
    setDetail(null)
    setDetailLoading(false)
    setError('')
    window.scrollTo(0, 0)
  }

  const refresh = useCallback(async ({ quiet = false } = {}) => {
    if (quiet) setRefreshing(true)
    else setLoading(true)
    setError('')
    try { setTasks(await getWorkerTasks()) }
    catch (requestError) { setError(requestError.message || 'Could not load assigned work.') }
    finally { setLoading(false); setRefreshing(false) }
  }, [])

  useEffect(() => {
    let active = true
    getWorkerTasks()
      .then(value => { if (active) setTasks(value) })
      .catch(requestError => { if (active) setError(requestError.message || 'Could not load assigned work.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!selected) return
    let active = true
    getWorkerComplaint(selected)
      .then(value => { if (active) setDetail(value) })
      .catch(requestError => { if (active) setError(requestError.message || 'Could not load this task.') })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selected])

  const pending = tasks.filter(task => task.status === 'ASSIGNED').length
  const active = tasks.filter(task => task.status === 'IN_PROGRESS').length
  const done = tasks.filter(task => task.status === 'COMPLETED').length
  const visibleTasks = useMemo(() => tasks.filter(task => {
    if (filter === 'active') return task.status !== 'COMPLETED'
    if (filter === 'pending') return task.status === 'ASSIGNED'
    if (filter === 'completed') return task.status === 'COMPLETED'
    return true
  }), [filter, tasks])
  const currentTask = tasks.find(task => String(task.complaint_id) === String(selected))

  async function update(status) {
    if (!currentTask) return
    setSaving(true)
    setError('')
    try {
      await updateWorkerTask(currentTask.id, { status, note: note.trim() || null })
      setNote('')
      await refresh({ quiet: true })
      setDetail(await getWorkerComplaint(selected))
    } catch (requestError) {
      setError(requestError.message || 'The task could not be updated. Please try again.')
    } finally { setSaving(false) }
  }

  return <div className="warden-app worker-app">
    <header className="warden-topbar">
      <a className="warden-brand" href="/worker/dashboard" onClick={event => { event.preventDefault(); closeComplaint() }}>
        <span className="warden-brand-mark"><LogoIcon /></span><span>HostelDesk<small>WORKER PORTAL</small></span>
      </a>
      <div className="warden-user"><span className="warden-avatar">{profile.name.slice(0, 1).toUpperCase()}</span><span>{profile.name}<small>{profile.email}</small></span><button type="button" className="student-link" onClick={onSignOut}>Sign out</button></div>
    </header>

    <main className="worker-main">
      {!selected ? <>
        <header className="worker-hero">
          <div><p className="warden-kicker">Maintenance workspace</p><h1>Good work starts with a clear queue.</h1><p>Review your assignments, update progress, and keep the hostel team in the loop.</p></div>
          <button type="button" className="button button--secondary worker-refresh" onClick={() => refresh({ quiet: true })} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh tasks'}</button>
        </header>

        <div className="worker-metrics">
          <WorkerMetric label="To start" value={pending} tone="amber" helper="Assigned and ready" />
          <WorkerMetric label="In progress" value={active} tone="blue" helper="Work underway" />
          <WorkerMetric label="Completed" value={done} tone="green" helper="Closed assignments" />
        </div>

        <section className="worker-queue" aria-labelledby="worker-queue-title">
          <div className="worker-queue__heading"><div><p className="warden-kicker">Your assignments</p><h2 id="worker-queue-title">Work queue</h2></div>
            <div className="worker-filter" role="tablist" aria-label="Filter assigned work">
              {[['active', 'Open', pending + active], ['pending', 'To start', pending], ['completed', 'Completed', done], ['all', 'All', tasks.length]].map(([key, label, count]) => <button key={key} type="button" role="tab" aria-selected={filter === key} className={filter === key ? 'is-active' : ''} onClick={() => setFilter(key)}>{label}<span>{count}</span></button>)}
            </div>
          </div>
          {error && !selected && <p className="warden-error" role="alert">{error}<button type="button" className="warden-inline-button" onClick={() => refresh()}>Retry</button></p>}
          {loading ? <p className="warden-state" role="status">Loading assigned work…</p> : visibleTasks.length ? <div className="worker-task-grid">{visibleTasks.map(task => <TaskCard key={task.id} task={task} onOpen={() => openComplaint(task.complaint_id)} />)}</div> : <div className="worker-empty"><span className="worker-empty__mark" aria-hidden="true">✓</span><h3>{filter === 'completed' ? 'Nothing completed yet' : filter === 'pending' ? 'You’re all caught up' : 'No tasks in this view'}</h3><p>{filter === 'completed' ? 'Completed tasks will appear here.' : 'New assignments from the Warden will show up here.'}</p></div>}
        </section>
      </> : <>
        <button type="button" className="warden-back worker-back" onClick={closeComplaint}>← Back to work queue</button>
        {detailLoading && <p className="warden-state" role="status">Loading task details…</p>}
        {error && <p className="warden-error" role="alert">{error}</p>}
        {detail && <>
          <header className="worker-detail-heading"><div><p className="warden-kicker">Assigned maintenance task</p><h1>Complaint #{detail.id}</h1><p>Submitted {date(detail.created_at)}</p></div><TaskState status={currentTask?.status || detail.status} /></header>
          <div className="worker-detail-grid">
            <section className="warden-card worker-report-card">
              <div className="worker-detail-tags"><TaskState status={currentTask?.status || detail.status} /><span className={`warden-badge priority-${(detail.severity || 'none').toLowerCase()}`}>{human(detail.severity)} priority</span></div>
              <p className="worker-detail-description">{detail.description}</p>
              <dl className="warden-details"><div><dt>Location</dt><dd>Block {detail.block}, Room {detail.room}</dd></div><div><dt>Category</dt><dd>{human(detail.category)}</dd></div><div><dt>Priority</dt><dd>{human(detail.severity)}</dd></div><div><dt>Assigned</dt><dd>{date(currentTask?.assigned_at)}</dd></div></dl>
              {detail.worker_note && <p className="worker-completion-note"><strong>Completion note</strong>{detail.worker_note}</p>}
              <h2>Progress history</h2>
              {detail.history?.length ? <ol className="warden-history">{detail.history.map((entry, index) => <li key={`${entry.created_at}-${index}`}><strong>{human(entry.new_status)}</strong><span>{date(entry.created_at)}{entry.note ? ` · ${entry.note}` : ''}</span></li>)}</ol> : <p className="warden-state">No progress updates yet.</p>}
            </section>
            <aside className="warden-card worker-action-card">
              <p className="warden-kicker">Next step</p><h2>{currentTask?.status === 'ASSIGNED' ? 'Start this task' : currentTask?.status === 'IN_PROGRESS' ? 'Mark the work complete' : 'Task completed'}</h2>
              {currentTask?.status === 'ASSIGNED' && <><p className="worker-action-copy">Start when you’re ready to work on this assignment. The Warden will see the status update.</p><button type="button" className="button button--primary" disabled={saving} onClick={() => update('IN_PROGRESS')}>{saving ? 'Updating…' : 'Start work'}</button></>}
              {currentTask?.status === 'IN_PROGRESS' && <div className="worker-actions">
                <p className="worker-action-copy">Add a short note describing what you fixed before closing this task.</p>
                <label htmlFor="completion-note">Completion note<textarea id="completion-note" rows="4" maxLength="1000" value={note} onChange={event => setNote(event.target.value)} placeholder="Example: Replaced the faulty switch and tested the fan." /></label>
                <div className="worker-note-count"><span>Visible to the Warden</span><span>{note.length}/1000 · 5 characters minimum</span></div>
                {note.trim().length > 0 && note.trim().length < 5 && <p className="ai-line ai-line--warn" role="status">Add a little more detail to your completion note.</p>}
                <button type="button" className="button button--primary" disabled={saving || note.trim().length < 5} onClick={() => update('COMPLETED')}>{saving ? 'Saving update…' : 'Mark completed'}</button>
              </div>}
              {currentTask?.status === 'COMPLETED' && <div className="worker-complete-state"><strong>Work closed</strong><span>The Warden can review your completion note from the complaint record.</span></div>}
            </aside>
          </div>
        </>}
      </>}
    </main>
  </div>
}

export default function WorkerApp() {
  return <RoleGate role="worker" dashboard={<WorkerWorkspace />} />
}
