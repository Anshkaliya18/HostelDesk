import { useEffect, useEffectEvent, useState } from 'react'
import {
  aiSweep, getAlerts, getComplaint, getComplaints, getDashboard,
  getDigest, getPhoto, getReports, getWorkers, reanalyzeComplaint, reviewComplaint,
} from '../../services/warden.js'
import { LogoIcon } from '../../components/Icons.jsx'
import { RoleGate } from '../RoleApp.jsx'
import '../portal.css'

// Bounded background sweep: fire-and-forget at most once per page load.
let sweepFired = false
function maybeSweep() {
  if (sweepFired) return
  sweepFired = true
  aiSweep()
}

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

function digestText(digest) {
  const categories = Object.entries(digest.category_counts || {}).filter(([, count]) => count > 0)
  const lines = [
    `HostelDesk daily digest — ${digest.date}`,
    `Summary source: ${digest.generated_by === 'ai' ? 'AI-assisted wording' : 'Deterministic rules'}`,
    '',
    digest.summary,
    '',
    `Open: ${digest.open_complaints} | Waiting for review: ${digest.stale_review} | Overdue: ${digest.overdue_complaints} | Completed today: ${digest.completed_complaints} | Repeat issues: ${digest.recurring_issues}`,
  ]
  if (categories.length) lines.push('', 'New reports by category:', ...categories.map(([name, count]) => `- ${human(name)}: ${count}`))
  if (digest.hotspots?.length) lines.push('', '30-day hotspots:', ...digest.hotspots.map(item => `- ${item.block} Block · ${human(item.category)} · ${item.count} reports`))
  if (digest.oldest_open) lines.push('', `Oldest open complaint: #${digest.oldest_open.id} · Block ${digest.oldest_open.block}, Room ${digest.oldest_open.room} · ${Math.round(digest.oldest_open.age_hours)} hours open`)
  if (digest.highlights?.length) lines.push('', 'Highlights:', ...digest.highlights.map(item => `- ${item}`))
  return lines.join('\n')
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return } catch { /* use the local fallback below */ }
  }
  const input = document.createElement('textarea')
  input.value = text
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.opacity = '0'
  document.body.append(input)
  input.select()
  const copied = document.execCommand('copy')
  input.remove()
  if (!copied) throw new Error('Clipboard access is unavailable in this browser.')
}

/** Shareable daily briefing with the deterministic counts kept visible. */
export function DigestCard({ digest, compact = false, onOpenAlert, onOpenComplaint }) {
  const [notice, setNotice] = useState('')
  const categories = Object.entries(digest.category_counts || {}).filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1])
  const categoryMaximum = Math.max(1, ...categories.map(([, count]) => count))

  async function handleCopy() {
    try { await copyText(digestText(digest)); setNotice('Digest copied to clipboard.') }
    catch (error) { setNotice(error.message || 'Could not copy the digest.') }
  }

  function handleDownload() {
    const file = new Blob([digestText(digest)], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(file)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `hosteldesk-digest-${digest.date}.txt`
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    setNotice('Digest downloaded.')
  }

  return <section className={`warden-card digest-card${compact ? ' digest-card--compact' : ''}`} aria-labelledby="digest-title">
    <div className="digest-head">
      <div className="digest-title-group">
        <p className="digest-eyebrow">Daily operations briefing</p>
        <h2 id="digest-title">{compact ? 'Today’s digest' : 'Daily digest report'}</h2>
      </div>
      <span className={`digest-source ${digest.generated_by === 'ai' ? 'digest-source--ai' : ''}`}>
        <span aria-hidden="true" />{digest.generated_by === 'ai' ? 'AI-assisted summary' : 'Rules-based summary'}
      </span>
      <div className="digest-actions">
        <button type="button" className="button button--secondary" onClick={handleCopy}>Copy</button>
        <button type="button" className="button button--secondary" onClick={handleDownload}>Download .txt</button>
      </div>
    </div>

    <div className="digest-summary-block">
      <span className="digest-summary-label">Executive summary</span>
      <p className="digest-summary">{digest.summary}</p>
    </div>

    <div className="digest-kpis" aria-label="Daily digest metrics">
      <div><span>Open</span><strong>{digest.open_complaints}</strong></div>
      <div className={digest.stale_review ? 'is-attention' : ''}><span>Review waiting</span><strong>{digest.stale_review}</strong></div>
      <div className={digest.overdue_complaints ? 'is-danger' : ''}><span>Overdue</span><strong>{digest.overdue_complaints}</strong></div>
      <div className="is-positive"><span>Completed today</span><strong>{digest.completed_complaints}</strong></div>
      <div><span>Repeat issues</span><strong>{digest.recurring_issues}</strong></div>
    </div>

    {!compact && <div className="digest-insights-grid">
      <section className="digest-insight-panel" aria-labelledby="digest-category-title">
        <div className="digest-section-heading"><div><p className="digest-eyebrow">New submissions</p><h3 id="digest-category-title">Category mix</h3></div><span>{categories.reduce((total, [, count]) => total + count, 0)} reports</span></div>
        {categories.length ? <div className="digest-category-list">{categories.map(([category, count]) => <div className="digest-category-row" key={category}>
          <div className="digest-category-label"><span>{human(category)}</span><strong>{count}</strong></div>
          <div className="digest-bar" aria-label={`${count} ${human(category)} reports`}><span style={{ width: `${Math.max(4, (count / categoryMaximum) * 100)}%` }} /></div>
        </div>)}</div> : <p className="digest-empty">No new reports for this date.</p>}
      </section>

      <section className="digest-insight-panel" aria-labelledby="digest-focus-title">
        <div className="digest-section-heading"><div><p className="digest-eyebrow">Needs attention</p><h3 id="digest-focus-title">Operations focus</h3></div></div>
        {digest.oldest_open ? <button type="button" className="digest-oldest" onClick={() => onOpenComplaint?.(digest.oldest_open.id)}>
          <span className="digest-oldest__label">Oldest open report · {Math.round(digest.oldest_open.age_hours)}h</span>
          <strong>Complaint #{digest.oldest_open.id}</strong>
          <span>Block {digest.oldest_open.block}, Room {digest.oldest_open.room}</span>
          <small>Open complaint →</small>
        </button> : <p className="digest-empty">No open complaints. The queue is clear.</p>}
        {digest.highlights?.length ? <ul className="digest-highlights">{digest.highlights.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : null}
      </section>

      <section className="digest-insight-panel digest-insight-panel--wide" aria-labelledby="digest-hotspots-title">
        <div className="digest-section-heading"><div><p className="digest-eyebrow">Last 30 days</p><h3 id="digest-hotspots-title">Recurring hotspots</h3></div><span>Top {digest.hotspots?.length || 0}</span></div>
        {digest.hotspots?.length ? <div className="digest-hotspots">{digest.hotspots.map((item, index) => <button type="button" className="digest-hotspot" key={`${item.block}-${item.category}`} onClick={() => onOpenAlert?.({ block: item.block, category: item.category })}>
          <span className="digest-hotspot__rank">0{index + 1}</span>
          <span className="digest-hotspot__copy"><strong>{item.block} Block · {human(item.category)}</strong><small>Recurring reports in this area</small></span>
          <span className="digest-hotspot__count">{item.count}<small>reports</small></span>
        </button>)}</div> : <p className="digest-empty">No recurring hotspots detected in the last 30 days.</p>}
      </section>
    </div>}
    <div className="digest-footer"><span>Report date · {digest.date} UTC</span><span>Counts are deterministic; AI only rephrases the summary.</span></div>
    {notice && <p className="digest-notice" role="status">{notice}</p>}
  </section>
}

function Dashboard() {
  const { data, loading, error } = useLoad(getDashboard)
  const [digest, setDigest] = useState(null)
  const [digestError, setDigestError] = useState('')
  useEffect(() => { getDigest().then(setDigest).catch(error => setDigestError(error.message || 'Digest unavailable.')) }, [])
  maybeSweep()
  return <><PageTitle title="Warden overview" subtitle="Complaint activity and worker workload at a glance." />
    <State loading={loading} error={error}>
      {data && <>
        {digest && <DigestCard digest={digest} compact />}
        {digestError && <p className="warden-error" role="alert">Daily digest unavailable: {digestError}</p>}
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

function SafetyBadge() {
  return <span className="warden-badge priority-safety">Safety risk</span>
}

function ComplaintTable({ complaints = [], onSelect }) {
  if (!complaints.length) return <p className="warden-state">No complaints match these filters.</p>
  return <div className="warden-table-wrap"><table className="warden-table complaint-table"><thead><tr><th>Complaint</th><th>Student / room</th><th>Category</th><th>Priority</th><th>Status</th><th>Submitted</th><th><span className="visually-hidden">Action</span></th></tr></thead>
    <tbody>{complaints.map(c => <tr key={c.id}>
      <td><div className="complaint-table-id"><strong>#{c.id}</strong>{c.ai_safety_flag ? <SafetyBadge /> : null}</div><span className="warden-truncate">{c.description}</span></td><td>{c.student?.name || 'Student'}<span className="warden-muted">Block {c.block}, Room {c.room}</span></td>
      <td>{human(c.category)}</td><td><span className={`warden-badge priority-${(c.severity || 'none').toLowerCase()}`}>{human(c.severity)}</span></td>
      <td><span className={`warden-badge status-${(c.status || 'unknown').toLowerCase().replaceAll('_', '-')}`}>{human(c.status)}</span></td><td><time dateTime={c.created_at}>{date(c.created_at)}</time></td>
      <td><button type="button" className="complaint-open-button" onClick={() => onSelect?.(c.id)} aria-label={`Review complaint ${c.id}`}>Review <span aria-hidden="true">→</span></button></td>
    </tr>)}</tbody></table></div>
}

function WorkerTable({ workers = [] }) {
  if (!workers.length) return <p className="warden-state">No worker profiles found.</p>
  return <div className="warden-table-wrap"><table className="warden-table"><thead><tr><th>Worker</th><th>Trade</th><th>Open tasks</th><th>Availability</th></tr></thead><tbody>
    {workers.map(w => <tr key={w.id}><td>{w.name}</td><td>{human(w.worker_type)}</td><td>{w.active_tasks}</td><td><span className={`warden-badge ${w.is_active ? 'badge-active' : 'badge-inactive'}`}>{w.is_active ? 'Available' : 'Inactive'}</span></td></tr>)}
  </tbody></table></div>
}

function Complaints({ onSelect }) {
  // Repeat-problem alerts in Reports deep-link here with a preset block/category.
  const preset = window.history.state?.hdPreset || null
  const [filters, setFilters] = useState({
    search: '', block: preset?.block || '', needs_review: false,
    status: '', category: preset?.category || '', severity: '', sort: 'newest',
  })
  const [searchInput, setSearchInput] = useState('')
  const { data, loading, error, refresh } = useLoad(() => getComplaints(filters), [filters])
  maybeSweep()
  useEffect(() => {
    const timer = window.setTimeout(() => setFilters(current => current.search === searchInput ? current : { ...current, search: searchInput }), 250)
    return () => window.clearTimeout(timer)
  }, [searchInput])
  const update = (key, value) => setFilters(current => {
    const next = { ...current, [key]: value }
    // Quick filter and review sort work together; an explicit status goes back
    // to the normal sort.
    if (key === 'needs_review' && value) next.sort = 'review'
    if (key === 'status' && value) next.needs_review = false
    return next
  })
  const clearFilters = () => {
    setSearchInput('')
    setFilters({ search: '', block: '', needs_review: false, status: '', category: '', severity: '', sort: 'newest' })
  }
  const activeFilters = [
    searchInput && ['search', `Search: ${searchInput}`],
    filters.block && ['block', `Block: ${filters.block}`],
    filters.needs_review && ['needs_review', 'Needs review'],
    filters.status && ['status', `Status: ${human(filters.status)}`],
    filters.category && ['category', `Category: ${human(filters.category)}`],
    filters.severity && ['severity', `Priority: ${human(filters.severity)}`],
  ].filter(Boolean)
  function removeFilter(key) {
    if (key === 'search') setSearchInput('')
    update(key, key === 'needs_review' ? false : '')
  }
  return <><PageTitle title="Complaint queue" subtitle="Search, filter, and review reports from across the hostel." />
    <section className="warden-card complaint-queue-card"><div className="complaint-queue-toolbar">
      <p className="complaint-result-count" aria-live="polite"><strong>{loading && !data ? '—' : data?.length ?? 0}</strong><span>{data?.length === 1 ? 'complaint' : 'complaints'}{activeFilters.length ? ' match these filters' : ' in the queue'}</span></p>
      <button type="button" className="button button--secondary complaint-refresh" onClick={refresh} disabled={loading}>{loading ? 'Updating…' : 'Refresh queue'}</button>
    </div><div className="warden-filters">
      <label className="warden-search">Search<input value={searchInput} onChange={e => setSearchInput(e.target.value)} placeholder="Description, student, block, room" /></label>
      <label>Block<input value={filters.block} onChange={e => update('block', e.target.value)} maxLength={40} placeholder="All blocks" /></label>
      <label><span className="warden-checkbox"><input type="checkbox" checked={filters.needs_review} onChange={e => update('needs_review', e.target.checked)} />Needs review</span></label>
      <label>Status<select value={filters.status} onChange={e => update('status', e.target.value)}><option value="">All status</option>{['SUBMITTED', 'AI_ANALYZED', 'WARDEN_REVIEW', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Category<select value={filters.category} onChange={e => update('category', e.target.value)}><option value="">All categories</option>{['ELECTRICAL', 'PLUMBING', 'CLEANING', 'FURNITURE'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Priority<select value={filters.severity} onChange={e => update('severity', e.target.value)}><option value="">Any priority</option>{['HIGH', 'MEDIUM', 'LOW'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
      <label>Sort<select value={filters.sort} onChange={e => update('sort', e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="updated">Recently updated</option><option value="review">Oldest unreviewed first</option></select></label>
      {activeFilters.length > 0 && <button type="button" className="button button--secondary complaint-clear" onClick={clearFilters}>Clear filters</button>}
    </div>
    {activeFilters.length > 0 && <div className="complaint-active-filters" aria-label="Active filters"><span>Filtered by</span>{activeFilters.map(([key, label]) => <button type="button" key={key} onClick={() => removeFilter(key)}>{label}<span aria-hidden="true">×</span></button>)}</div>}
    <State loading={loading} error={error} empty={data?.length === 0 ? 'No complaints match these filters. Try clearing one or more filters.' : null}>
        {data && <ComplaintTable complaints={data} onSelect={onSelect} />}
      </State></section>
  </>
}

function ComplaintDetail({ id, onBack, onUpdated, onOpen }) {
  const { data, loading, error, refresh } = useLoad(() => getComplaint(id), [id])
  const [workerId, setWorkerId] = useState('')
  const [category, setCategory] = useState('')
  const [severity, setSeverity] = useState('')
  const [note, setNote] = useState('')
  const [workers, setWorkers] = useState([])
  const [photo, setPhoto] = useState(null)
  const [saving, setSaving] = useState(false)
  const [refetching, setRefetching] = useState(false)
  const [actionError, setActionError] = useState('')
  useEffect(() => { getWorkers().then(setWorkers).catch(e => setActionError(e.message)) }, [])
  useEffect(() => { let url; getPhoto(id).then(result => { url = result; setPhoto(result) }); return () => { if (url) URL.revokeObjectURL(url) } }, [id])

  const recommendation = data?.ai_recommendation && data.ai_recommendation.category ? data.ai_recommendation : null
  const aiTrade = recommendation?.suggested_worker || data?.ai_suggested_worker || null

  // Workers matching the AI trade come first, each group by fewest active tasks.
  const orderedWorkers = [...workers.filter(w => w.is_active)]
    .sort((a, b) => Number(b.worker_type === aiTrade) - Number(a.worker_type === aiTrade) || a.active_tasks - b.active_tasks)
  const bestMatch = orderedWorkers[0] || null

  // Fall back to the best match while the warden hasn't chosen explicitly,
  // so "Approve AI suggestion" always targets it without an effect.
  const effectiveWorkerId = workerId || (bestMatch ? String(bestMatch.id) : '')
  const selectedWorker = workers.find(w => String(w.id) === String(effectiveWorkerId)) || null
  const tradeMismatch = Boolean(selectedWorker && aiTrade && selectedWorker.worker_type !== aiTrade)

  async function submitReview(event) {
    event.preventDefault(); setSaving(true); setActionError('')
    try { await reviewComplaint(id, { category: category || data.category || data.ai_recommendation?.category || 'ELECTRICAL', severity: severity || data.severity || data.ai_recommendation?.severity || 'MEDIUM', worker_id: Number(workerId), warden_note: note || data.warden_note || null }); await refresh(); onUpdated() }
    catch (e) { setActionError(e.message) } finally { setSaving(false) }
  }

  async function approveAiSuggestion() {
    if (!recommendation || !bestMatch) return
    setSaving(true); setActionError('')
    try { await reviewComplaint(id, { category: recommendation.category, severity: recommendation.severity, worker_id: bestMatch.id, warden_note: note || data.warden_note || null }); await refresh(); onUpdated() }
    catch (e) { setActionError(e.message) } finally { setSaving(false) }
  }

  async function rerunAi() {
    setRefetching(true); setActionError('')
    try { await reanalyzeComplaint(id); await refresh() }
    catch (e) { setActionError(e.message) } finally { setRefetching(false) }
  }

  return <><button className="warden-back" onClick={onBack}>← All complaints</button><State loading={loading} error={error}>
    {data && <><PageTitle title={`Complaint #${data.id}`} subtitle={`Submitted ${date(data.created_at)} · Updated ${date(data.updated_at)}`} />
      <div className="warden-columns complaint-detail-grid"><section className="warden-card complaint-report-card">
        <div className="detail-heading"><span className={`warden-badge`}>{human(data.status)}</span><span className={`warden-badge priority-${(data.severity || 'none').toLowerCase()}`}>{human(data.severity)} priority</span>{(recommendation?.safety_flag || data.ai_safety_flag) ? <SafetyBadge /> : null}</div>
        <h2>Report</h2><p className="complaint-description">{data.description}</p>
        <dl className="warden-details"><div><dt>Student</dt><dd>{data.student.name}</dd></div><div><dt>Location</dt><dd>Block {data.block}, Room {data.room}</dd></div><div><dt>Category</dt><dd>{human(data.category)}</dd></div><div><dt>Assigned worker</dt><dd>{data.approved_worker?.name || 'Not assigned'}</dd></div></dl>
        {photo && <img className="complaint-photo" src={photo} alt={`Photo attached to complaint ${data.id}`} />}
        <h2>Status history</h2><ol className="warden-history">{data.history.map((h, i) => <li key={`${h.created_at}-${i}`}><strong>{human(h.new_status)}</strong><span>{date(h.created_at)}{h.note ? ` · ${h.note}` : ''}</span></li>)}</ol>
      </section><aside className="warden-card complaint-review-card">
          <h2>AI recommendation</h2><p className="warden-muted">AI suggestions are advisory. You make the final assignment.</p>
          <div className="recommendation"><span>Category</span><strong>{human(recommendation?.category || data.category)}</strong><span>Severity</span><strong>{human(recommendation?.severity || data.severity)}</strong><span>Suggested trade</span><strong>{human(data.ai_suggested_worker)}</strong></div>
          {recommendation ? (
            <div className="ai-extra">
              {recommendation.reason ? <p className="ai-reason">Why: {recommendation.reason}</p> : null}
              {recommendation.confidence ? <p className="ai-line">Confidence: {human(recommendation.confidence)}</p> : null}
              {recommendation.safety_flag ? <SafetyBadge /> : null}
              {recommendation.duplicate_of_complaint_id ? (
                <p className="ai-line">Possible duplicate of{' '}
                  <a className="warden-link" href={`/warden/complaints/${recommendation.duplicate_of_complaint_id}`}
                    onClick={e => { e.preventDefault(); onOpen?.(recommendation.duplicate_of_complaint_id) }}>
                    #{recommendation.duplicate_of_complaint_id}
                  </a>
                </p>
              ) : null}
              <p className="ai-line">Model: {recommendation.model || 'unknown'}</p>
            </div>
          ) : (
            <div className="ai-extra">
              {data.ai_suggested_worker ? <p className="ai-line">Suggested worker: {human(data.ai_suggested_worker)}</p> : null}
              {data.ai_recommendation && !data.ai_recommendation.category
                ? <p className="ai-line ai-line--warn">The last analysis could not produce a suggestion.</p>
                : null}
              {['SUBMITTED', 'AI_ANALYZED', 'WARDEN_REVIEW'].includes(data.status) ? (
                <button type="button" className="button button--secondary" disabled={refetching} onClick={rerunAi}>
                  {refetching ? 'Re-running AI…' : 'Re-run AI'}
                </button>
              ) : null}
            </div>
          )}
          {['SUBMITTED', 'AI_ANALYZED', 'WARDEN_REVIEW'].includes(data.status) ? <form className="warden-review-form" onSubmit={submitReview}><h2>Review and assign</h2>
            {recommendation ? <button type="button" className="button button--primary" disabled={saving || !bestMatch || refetching} onClick={approveAiSuggestion}>{saving ? 'Saving…' : 'Approve AI suggestion'}</button> : null}
            <label>Final category<select required value={category || data.category || data.ai_recommendation?.category || 'ELECTRICAL'} onChange={e => setCategory(e.target.value)}>{['ELECTRICAL', 'PLUMBING', 'CLEANING', 'FURNITURE'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
            <label>Priority<select required value={severity || data.severity || data.ai_recommendation?.severity || 'MEDIUM'} onChange={e => setSeverity(e.target.value)}>{['HIGH', 'MEDIUM', 'LOW'].map(s => <option key={s} value={s}>{human(s)}</option>)}</select></label>
            <label>Assign worker<select required value={effectiveWorkerId} onChange={e => setWorkerId(e.target.value)}><option value="">Choose a worker</option>{orderedWorkers.map(w => <option key={w.id} value={w.id}>{w.name} · {human(w.worker_type)} · {w.active_tasks} active{aiTrade && w.worker_type === aiTrade ? ' · AI match' : ''}</option>)}</select></label>
            {tradeMismatch ? <p className="ai-line ai-line--warn" role="status">Different trade than AI suggested.</p> : null}
            <label>Warden note<textarea value={note} onChange={e => setNote(e.target.value)} rows="3" maxLength="1000" /></label>
            {actionError && <p role="alert" className="warden-error">{actionError}</p>}<button className="button button--secondary" disabled={saving || !effectiveWorkerId}>{saving ? 'Saving…' : 'Approve and assign'}</button>
          </form> : <p className="warden-assignment-note">Assignment is active. Workers update task progress from their task view.</p>}
        </aside></div></>}
    {actionError && !data && <p className="warden-error">{actionError}</p>}
  </State></>
}

function Workers() { const { data, loading, error } = useLoad(getWorkers); return <><PageTitle title="Workers" subtitle="Availability and active assigned work." /><section className="warden-card"><State loading={loading} error={error} empty={data?.length === 0 ? 'No workers found.' : null}>{data && <WorkerTable workers={data} />}</State></section></> }

function Reports({ onOpenAlert, onOpenComplaint }) {
  const today = new Date().toISOString().slice(0, 10)
  const [digestDate, setDigestDate] = useState(today)
  const [refreshKey, setRefreshKey] = useState(0)
  const [reportsState, setReportsState] = useState({ loading: true, error: '', data: null })
  const [alertsState, setAlertsState] = useState({ loading: true, error: '', data: [] })
  const [digestState, setDigestState] = useState({ loading: true, error: '', data: null })

  useEffect(() => {
    let active = true
    getReports().then(data => { if (active) setReportsState({ loading: false, error: '', data }) })
      .catch(error => { if (active) setReportsState(state => ({ ...state, loading: false, error: error.message })) })
    getAlerts().then(data => { if (active) setAlertsState({ loading: false, error: '', data }) })
      .catch(error => { if (active) setAlertsState(state => ({ ...state, loading: false, error: error.message })) })
    return () => { active = false }
  }, [refreshKey])

  useEffect(() => {
    let active = true
    getDigest(digestDate).then(data => { if (active) setDigestState({ loading: false, error: '', data }) })
      .catch(error => { if (active) setDigestState({ loading: false, error: error.message, data: null }) })
    return () => { active = false }
  }, [digestDate, refreshKey])

  const data = reportsState.data
  const digest = digestState.data
  const alerts = alertsState.data
  function refreshReport() {
    setReportsState(state => ({ ...state, loading: true, error: '' }))
    setAlertsState(state => ({ ...state, loading: true, error: '' }))
    setDigestState({ loading: true, error: '', data: null })
    setRefreshKey(value => value + 1)
  }
  function changeDigestDate(value) {
    setDigestState({ loading: true, error: '', data: null })
    setDigestDate(value)
  }

  return <>
    <PageTitle title="Reports and insights" subtitle="A clear daily briefing, workload signals, and repeat-problem patterns." />
    <div className="reports-toolbar">
      <label className="reports-date">Digest date<input type="date" value={digestDate} max={today} onChange={event => changeDigestDate(event.target.value)} /></label>
      <p className="reports-timezone">Daily counts use UTC.</p>
      <button type="button" className="button button--secondary reports-refresh" disabled={reportsState.loading || alertsState.loading || digestState.loading} onClick={refreshReport}>
        {reportsState.loading || alertsState.loading || digestState.loading ? 'Refreshing…' : 'Refresh report'}
      </button>
    </div>

    {digestState.error && <div className="warden-error reports-error" role="alert"><span>Digest unavailable: {digestState.error}</span><button type="button" className="warden-inline-button" onClick={refreshReport}>Try again</button></div>}
    {digestState.loading && !digest && <p className="warden-state" role="status">Building the daily digest…</p>}
    {digest && <>
      <DigestCard digest={digest} onOpenAlert={onOpenAlert} onOpenComplaint={onOpenComplaint} />
    </>}

    <div className="reports-section-heading"><div><p className="warden-kicker">Live operational view</p><h2>Queue health</h2></div>{reportsState.error && <span className="reports-inline-error" role="alert">{reportsState.error}</span>}</div>
    {reportsState.loading && !data && <p className="warden-state" role="status">Loading queue insights…</p>}
    {data && <div className="warden-columns reports-columns">
      <section className="warden-card report-breakdown-card">
        <div className="digest-section-heading"><div><p className="digest-eyebrow">All-time snapshot</p><h3>Complaint status</h3></div></div>
        <div className="report-list">{Object.entries(data.by_status || {}).filter(([key]) => key !== 'AI_ANALYZED').map(([key, value]) => <div key={key}><span>{human(key)}</span><strong>{value}</strong></div>)}</div>
        <p className="report-principle"><strong>Review gate</strong><span>AI suggestions are advisory. Every assignment is confirmed by a Warden.</span></p>
        <div className="digest-section-heading report-category-heading"><div><p className="digest-eyebrow">All-time snapshot</p><h3>Category mix</h3></div></div>
        <div className="report-list">{Object.entries(data.by_category || {}).map(([key, value]) => <div key={key}><span>{human(key)}</span><strong>{value}</strong></div>)}</div>
      </section>
      <section className="warden-card report-alert-card">
        <div className="digest-section-heading"><div><p className="digest-eyebrow">Repeat patterns</p><h3>Active alerts</h3></div><span className="report-count">{alerts.length}</span></div>
        {alertsState.error && <p className="reports-inline-error" role="alert">Alerts could not load: {alertsState.error}</p>}
        {alertsState.loading && !alerts.length ? <p className="warden-state" role="status">Loading alerts…</p> : alerts.length ? <ul className="alert-list">{alerts.map(alert => <li key={alert.id}>
          <button type="button" className="alert-list__link" onClick={() => alert.block && onOpenAlert?.({ block: alert.block, category: alert.category || '' })}>
            <span className="alert-list__topline"><strong>{alert.block} Block · {human(alert.category)}</strong><span>{alert.complaint_count} reports</span></span>
            <span>{alert.message}</span><small>{date(alert.created_at)} · Open matching reports →</small>
          </button>
        </li>)}</ul> : <p className="warden-state">No active repeat-problem alerts.</p>}
      </section>
    </div>}
  </>
}

function WardenWorkspace({ profile, onSignOut }) {
  const [path, setPath] = useState(window.location.pathname)
  const [detailId, setDetailId] = useState(window.location.pathname.match(/^\/warden\/complaints\/(\d+)/)?.[1] || null)
  useEffect(() => { const handle = () => { setPath(window.location.pathname); setDetailId(window.location.pathname.match(/^\/warden\/complaints\/(\d+)/)?.[1] || null) }; window.addEventListener('popstate', handle); return () => window.removeEventListener('popstate', handle) }, [])
  function navigate(next, id = null, preset = null) {
    window.history.pushState(preset ? { hdPreset: preset } : {}, '', next)
    setPath(next); setDetailId(id ? String(id) : null); window.scrollTo(0, 0)
  }
  const route = detailId ? 'detail' : path.split('/')[2] || 'dashboard'
  return <div className="warden-app"><header className="warden-topbar"><a href="/warden/dashboard" onClick={e => { e.preventDefault(); navigate('/warden/dashboard') }} className="warden-brand"><span className="warden-brand-mark"><LogoIcon /></span><span>HostelDesk<small>WARDEN PORTAL</small></span></a><div className="warden-user"><span className="warden-avatar">{profile.name.slice(0, 1).toUpperCase()}</span><span>{profile.name}<small>{profile.email}</small></span><button className="student-link" onClick={onSignOut}>Sign out</button></div></header>
    <div className="warden-layout"><aside className="warden-sidebar"><p className="warden-nav-label">WORKSPACE</p>{links.map(([href, label]) => <a key={href} className={route === href.split('/')[2] || (route === 'detail' && label === 'Complaints') ? 'active' : ''} href={href} onClick={e => { e.preventDefault(); navigate(href) }}><span className="nav-dot" />{label}</a>)}<div className="sidebar-hint"><strong>Review gate</strong><span>AI suggests. You decide.</span></div></aside>
      <main className="warden-main"><div className="warden-mobile-nav">{links.map(([href, label]) => <a key={href} href={href} onClick={e => { e.preventDefault(); navigate(href) }} className={route === href.split('/')[2] ? 'active' : ''}>{label}</a>)}</div>
        {route === 'dashboard' && <Dashboard />}{route === 'complaints' && !detailId && <Complaints onSelect={id => navigate(`/warden/complaints/${id}`, id)} />}
        {route === 'detail' && <ComplaintDetail id={detailId} onBack={() => navigate('/warden/complaints')} onUpdated={() => { }} onOpen={dupId => navigate(`/warden/complaints/${dupId}`, dupId)} />}
        {route === 'workers' && <Workers />}{route === 'reports' && <Reports onOpenAlert={preset => navigate('/warden/complaints', null, preset)} onOpenComplaint={id => navigate(`/warden/complaints/${id}`, id)} />}
        {route === 'profile' && <><PageTitle title="Warden profile" subtitle="Your account details." /><section className="warden-card profile-card"><span className="profile-avatar">{profile.name.slice(0, 1).toUpperCase()}</span><div><h2>{profile.name}</h2><p>{profile.email}</p><p>Role: {profile.role}</p><p>Account ID: {profile.id}</p></div></section></>}
      </main></div>
  </div>
}

export default function WardenApp() {
  return <RoleGate role="warden" dashboard={<WardenWorkspace />} />
}
