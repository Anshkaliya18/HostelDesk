import { useEffect, useEffectEvent, useState } from 'react'
import {
  getAlerts, getComplaint, getComplaints, getDashboard,
  getDigest, getPhoto, getReports, getWorkers, reviewComplaint,
} from '../../services/warden.js'
import { RoleGate } from '../RoleApp.jsx'
import './warden.css'

const links = [
  ['/warden/dashboard', 'Overview'], ['/warden/complaints', 'Complaints'],
  ['/warden/workers', 'Workers'], ['/warden/reports', 'Reports'], ['/warden/profile', 'Profile'],
]
const human = value => value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : 'Unclassified'
const date = value => value ? new Date(value).toLocaleString() : '—'

function useLoad(loader, deps = []) {
  const [state, setState] = useState({ loading: true, error: '', data: null })
  const key = JSON.stringify(deps)
  const load = useEffectEvent(() => loader().then(data => setState({ loading: false, error: '', data }))
    .catch(error => setState({ loading: false, error: error.message, data: null })))
  function refresh() {
    setState({ loading: true, error: '', data: null })
    loader().then(data => setState({ loading: false, error: '', data }))
      .catch(error => setState({ loading: false, error: error.message, data: null }))
  }
  useEffect(() => { load() }, [key])
  return { ...state, refresh }
}

function State({ loading, error, empty, children }) {
  if (loading) return <p className="warden-state" role="status">Loading Warden data…</p>
  if (error) return <div className="warden-error" role="alert">{error}</div>
  if (empty) return <p className="warden-state">{empty}</p>
  return children
}

function Metric({ label, value, tone }) {
  return <article className={`warden-metric ${tone || ''}`}><span>{label}</span><strong>{value ?? '—'}</strong></article>
}

function Dashboard() {
  const { data, loading, error } = useLoad(getDashboard)
  return <><PageTitle title="Warden overview" subtitle="Complaint activity and worker workload at a glance." />
    <State loading={loading} error={error}>
      {data && <>
        <div className="warden-metrics">
          <Metric label="All complaints" value={data.total} /><Metric label="Awaiting review" value={data.pending} tone="amber" />
          <Metric label="In progress" value={data.in_progress} tone="blue" /><Metric label="Resolved" value={data.resolved} tone="green" />
          <Metric label="High priority open" value={data.high_priority} tone="red" />
        </div>
        <div className="warden-columns">
          <section className="warden-card"><h2>Recently submitted</h2><ComplaintTable complaints={data.recent} /></section>
          <section className="warden-card"><h2>Worker workload</h2><WorkerTable workers={data.workers} /></section>
        </div>
      </>}
    </State>
  </>
}

function PageTitle({ title, subtitle }) { return <header className="warden-page-title"><div><p className="warden-kicker">Hostel operations</p><h1>{title}</h1><p>{subtitle}</p></div></header> }

function ComplaintTable({ complaints = [], onSelect }) {
  if (!complaints.length) return <p className="warden-state">No complaints match these filters.</p>
  return <div className="warden-table-wrap"><table className="warden-table"><thead><tr><th>Complaint</th><th>Student / room</th><th>Category</th><th>Priority</th><th>Status</th><th>Submitted</th></tr></thead>
    <tbody>{complaints.map(c => <tr key={c.id} onClick={() => onSelect?.(c.id)} className={onSelect ? 'is-clickable' : ''}>
      <td><strong>#{c.id}</strong><span className="warden-truncate">{c.description}</span></td><td>{c.student?.name || 'Student'}<span className="warden-muted">Block {c.block}, Room {c.room}</span></td>
      <td>{human(c.category)}</td><td><span className={`warden-badge priority-${(c.severity || 'none').toLowerCase()}`}>{human(c.severity)}</span></td>
      <td><span className="warden-badge">{human(c.status)}</span></td><td>{date(c.created_at)}</td>
    </tr>)}</tbody></table></div>
}

function WorkerTable({ workers = [] }) {
  if (!workers.length) return <p className="warden-state">No worker profiles found.</p>
  return <div className="warden-table-wrap"><table className="warden-table"><thead><tr><th>Worker</th><th>Trade</th><th>Open tasks</th><th>Availability</th></tr></thead><tbody>
    {workers.map(w => <tr key={w.id}><td>{w.name}</td><td>{human(w.worker_type)}</td><td>{w.active_tasks}</td><td><span className={`warden-badge ${w.is_active ? 'badge-active' : 'badge-inactive'}`}>{w.is_active ? 'Available' : 'Inactive'}</span></td></tr>)}
  </tbody></table></div>
}

function Complaints({ onSelect }) {
  const [filters, setFilters] = useState({ search: '', status: '', category: '', severity: '', sort: 'newest' })
  const { data, loading, error, refresh } = useLoad(() => getComplaints(filters), [filters])
  const update = (key, value) => setFilters(current => ({ ...current, [key]: value }))
  return <><PageTitle title="Complaint queue" subtitle="Search, filter, and review reports from across the hostel." />
    <section className="warden-card"><div className="warden-filters">
      <label className="warden-search">Search<input value={filters.search} onChange={e => update('search', e.target.value)} placeholder="Description, student, block, room" /></label>
      <label>Status<select value={filters.status} onChange={e => update('status', e.target.value)}><option value="">All statuses</option>{['SUBMITTED','AI_ANALYZED','WARDEN_REVIEW','ASSIGNED','IN_PROGRESS','COMPLETED'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Category<select value={filters.category} onChange={e => update('category', e.target.value)}><option value="">All categories</option>{['ELECTRICAL','PLUMBING','CLEANING','FURNITURE'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Priority<select value={filters.severity} onChange={e => update('severity', e.target.value)}><option value="">Any priority</option>{['HIGH','MEDIUM','LOW'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Sort<select value={filters.sort} onChange={e => update('sort', e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="updated">Recently updated</option></select></label>
      <button className="button button--secondary" onClick={() => setFilters({ search: '', status: '', category: '', severity: '', sort: 'newest' })}>Clear</button>
    </div><State loading={loading} error={error} empty={data?.length === 0 ? 'No complaints match these filters.' : null}>
      {data && <ComplaintTable complaints={data} onSelect={onSelect} />}
    </State><button className="warden-refresh" onClick={refresh}>Refresh queue</button></section>
  </>
}

function ComplaintDetail({ id, onBack, onUpdated }) {
  const { data, loading, error, refresh } = useLoad(() => getComplaint(id), [id])
  const [workerId, setWorkerId] = useState('')
  const [category, setCategory] = useState('')
  const [severity, setSeverity] = useState('')
  const [note, setNote] = useState('')
  const [workers, setWorkers] = useState([])
  const [photo, setPhoto] = useState(null)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState('')
  useEffect(() => { getWorkers().then(setWorkers).catch(e => setActionError(e.message)) }, [])
  useEffect(() => { let url; getPhoto(id).then(result => { url = result; setPhoto(result) }); return () => { if (url) URL.revokeObjectURL(url) } }, [id])
  async function submitReview(event) {
    event.preventDefault(); setSaving(true); setActionError('')
    try { await reviewComplaint(id, { category: category || data.category || data.ai_recommendation?.category || 'ELECTRICAL', severity: severity || data.severity || data.ai_recommendation?.severity || 'MEDIUM', worker_id: Number(workerId), warden_note: note || data.warden_note || null }); await refresh(); onUpdated() }
    catch (e) { setActionError(e.message) } finally { setSaving(false) }
  }
  return <><button className="warden-back" onClick={onBack}>← All complaints</button><State loading={loading} error={error}>
    {data && <><PageTitle title={`Complaint #${data.id}`} subtitle={`Submitted ${date(data.created_at)} · Updated ${date(data.updated_at)}`} />
      <div className="warden-columns complaint-detail-grid"><section className="warden-card">
        <div className="detail-heading"><span className={`warden-badge`}>{human(data.status)}</span><span className={`warden-badge priority-${(data.severity || 'none').toLowerCase()}`}>{human(data.severity)} priority</span></div>
        <h2>Report</h2><p className="complaint-description">{data.description}</p>
        <dl className="warden-details"><div><dt>Student</dt><dd>{data.student.name}</dd></div><div><dt>Location</dt><dd>Block {data.block}, Room {data.room}</dd></div><div><dt>Category</dt><dd>{human(data.category)}</dd></div><div><dt>Assigned worker</dt><dd>{data.approved_worker?.name || 'Not assigned'}</dd></div></dl>
        {photo && <img className="complaint-photo" src={photo} alt={`Photo attached to complaint ${data.id}`} />}
        <h2>Status history</h2><ol className="warden-history">{data.history.map((h, i) => <li key={`${h.created_at}-${i}`}><strong>{human(h.new_status)}</strong><span>{date(h.created_at)}{h.note ? ` · ${h.note}` : ''}</span></li>)}</ol>
      </section><aside className="warden-card">
        <h2>AI recommendation</h2><p className="warden-muted">AI suggestions are advisory. You make the final assignment.</p>
        <div className="recommendation"><span>Category</span><strong>{human(data.ai_recommendation?.category || data.category)}</strong><span>Severity</span><strong>{human(data.ai_recommendation?.severity || data.severity)}</strong><span>Suggested trade</span><strong>{human(data.ai_recommendation?.suggested_worker || data.ai_suggested_worker)}</strong></div>
        {['SUBMITTED','AI_ANALYZED','WARDEN_REVIEW'].includes(data.status) ? <form className="warden-review-form" onSubmit={submitReview}><h2>Review and assign</h2>
          <label>Final category<select required value={category || data.category || data.ai_recommendation?.category || 'ELECTRICAL'} onChange={e => setCategory(e.target.value)}>{['ELECTRICAL','PLUMBING','CLEANING','FURNITURE'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
          <label>Priority<select required value={severity || data.severity || data.ai_recommendation?.severity || 'MEDIUM'} onChange={e => setSeverity(e.target.value)}>{['HIGH','MEDIUM','LOW'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
          <label>Assign worker<select required value={workerId} onChange={e => setWorkerId(e.target.value)}><option value="">Choose a worker</option>{workers.filter(w => w.is_active).map(w => <option key={w.id} value={w.id}>{w.name} · {human(w.worker_type)} · {w.active_tasks} active</option>)}</select></label>
          <label>Warden note<textarea value={note} onChange={e => setNote(e.target.value)} rows="3" maxLength="1000" /></label>
          {actionError && <p role="alert" className="warden-error">{actionError}</p>}<button className="button button--primary" disabled={saving || !workerId}>{saving ? 'Saving…' : 'Approve and assign'}</button>
        </form> : <p className="warden-assignment-note">Assignment is active. Workers update task progress from their task view.</p>}
      </aside></div></>}
    {actionError && !data && <p className="warden-error">{actionError}</p>}
  </State></>
}

function Workers() { const { data, loading, error } = useLoad(getWorkers); return <><PageTitle title="Workers" subtitle="Availability and active assigned work." /><section className="warden-card"><State loading={loading} error={error} empty={data?.length === 0 ? 'No workers found.' : null}>{data && <WorkerTable workers={data} />}</State></section></> }

function Reports() {
  const [data, setData] = useState(null); const [alerts, setAlerts] = useState([]); const [digest, setDigest] = useState(null); const [error, setError] = useState('')
  useEffect(() => { Promise.all([getReports(), getAlerts(), getDigest()]).then(([r, a, d]) => { setData(r); setAlerts(a); setDigest(d) }).catch(e => setError(e.message)) }, [])
  return <><PageTitle title="Reports and insights" subtitle="Daily operations, complaint mix, and repeat-problem alerts." /><State loading={!data && !error} error={error}>
    {data && <><div className="warden-metrics"><Metric label="Open complaints" value={digest.open_complaints} /><Metric label="Overdue" value={digest.overdue_complaints} tone="red" /><Metric label="Completed today" value={digest.completed_complaints} tone="green" /><Metric label="Recurring issues" value={digest.recurring_issues} tone="amber" /><Metric label="AI analyzed" value={data.ai_analyzed ?? 0} tone="amber" /></div>
      <div className="warden-columns"><section className="warden-card"><h2>Complaint status</h2><div className="report-list">{Object.entries(data.by_status).filter(([k]) => k !== 'AI_ANALYZED').map(([k,v]) => <div key={k}><span>{human(k)}</span><strong>{v}</strong></div>)}</div><p className="warden-muted">AI suggestions are generated seconds after submission, then complaints move straight to warden review — that is the review gate keeping the AI in the suggest-only role.</p><h2>Category mix</h2><div className="report-list">{Object.entries(data.by_category).map(([k,v]) => <div key={k}><span>{human(k)}</span><strong>{v}</strong></div>)}</div></section>
      <section className="warden-card"><h2>Repeat-problem alerts</h2>{alerts.length ? <ul className="alert-list">{alerts.map(a => <li key={a.id}><strong>{a.block} Block · {human(a.category)}</strong><span>{a.message}</span><small>{a.complaint_count} reports · {date(a.created_at)}</small></li>)}</ul> : <p className="warden-state">No active repeat-problem alerts.</p>}<h2>Today’s digest</h2><p className="warden-muted">{digest.date} · {digest.open_complaints} open · {digest.overdue_complaints} overdue · {digest.completed_complaints} completed</p></section></div></>}
  </State></>
}

function WardenWorkspace({ profile, onSignOut }) {
  const [path, setPath] = useState(window.location.pathname)
  const [detailId, setDetailId] = useState(window.location.pathname.match(/^\/warden\/complaints\/(\d+)/)?.[1] || null)
  useEffect(() => { const handle = () => { setPath(window.location.pathname); setDetailId(window.location.pathname.match(/^\/warden\/complaints\/(\d+)/)?.[1] || null) }; window.addEventListener('popstate', handle); return () => window.removeEventListener('popstate', handle) }, [])
  function navigate(next, id = null) { window.history.pushState({}, '', next); setPath(next); setDetailId(id ? String(id) : null); window.scrollTo(0, 0) }
  const route = detailId ? 'detail' : path.split('/')[2] || 'dashboard'
  return <div className="warden-app"><header className="warden-topbar"><a href="/warden/dashboard" onClick={e => { e.preventDefault(); navigate('/warden/dashboard') }} className="warden-brand"><span className="warden-brand-mark">H</span><span>HostelDesk<small>WARDEN PORTAL</small></span></a><div className="warden-user"><span className="warden-avatar">{profile.name.slice(0, 1).toUpperCase()}</span><span>{profile.name}<small>{profile.email}</small></span><button className="student-link" onClick={onSignOut}>Sign out</button></div></header>
    <div className="warden-layout"><aside className="warden-sidebar"><p className="warden-nav-label">WORKSPACE</p>{links.map(([href, label]) => <a key={href} className={route === href.split('/')[2] || (route === 'detail' && label === 'Complaints') ? 'active' : ''} href={href} onClick={e => { e.preventDefault(); navigate(href) }}><span className="nav-dot" />{label}</a>)}<div className="sidebar-hint"><strong>Review gate</strong><span>AI suggests. You decide.</span></div></aside>
      <main className="warden-main"><div className="warden-mobile-nav">{links.map(([href,label]) => <a key={href} href={href} onClick={e => { e.preventDefault(); navigate(href) }} className={route === href.split('/')[2] ? 'active' : ''}>{label}</a>)}</div>
        {route === 'dashboard' && <Dashboard />}{route === 'complaints' && !detailId && <Complaints onSelect={id => navigate(`/warden/complaints/${id}`, id)} />}
        {route === 'detail' && <ComplaintDetail id={detailId} onBack={() => navigate('/warden/complaints')} onUpdated={() => {}} />}
        {route === 'workers' && <Workers />}{route === 'reports' && <Reports />}
        {route === 'profile' && <><PageTitle title="Warden profile" subtitle="Your account details." /><section className="warden-card profile-card"><span className="profile-avatar">{profile.name.slice(0, 1).toUpperCase()}</span><div><h2>{profile.name}</h2><p>{profile.email}</p><p>Role: {profile.role}</p><p>Account ID: {profile.id}</p></div></section></>}
      </main></div>
  </div>
}

export default function WardenApp() {
  return <RoleGate role="warden" dashboard={<WardenWorkspace />} />
}
