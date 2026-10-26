import { useEffect, useState } from 'react'
import { RoleGate } from '../RoleApp.jsx'
import { getWorkerComplaint, getWorkerTasks, updateWorkerTask } from '../../services/roleApi.js'

const human = value => value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : '—'
function WorkerWorkspace({ profile, onSignOut }) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(window.location.pathname.match(/^\/worker\/complaints\/(\d+)/)?.[1] || null)
  const [detail, setDetail] = useState(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    const handle = () => setSelected(window.location.pathname.match(/^\/worker\/complaints\/(\d+)/)?.[1] || null)
    window.addEventListener('popstate', handle)
    return () => window.removeEventListener('popstate', handle)
  }, [])
  function openComplaint(id) { window.history.pushState({}, '', `/worker/complaints/${id}`); setSelected(String(id)); setDetail(null) }
  function closeComplaint() { window.history.pushState({}, '', '/worker/complaints'); setSelected(null); setDetail(null) }
  async function refresh() { setLoading(true); setError(''); try { setTasks(await getWorkerTasks()) } catch (e) { setError(e.message) } finally { setLoading(false) } }
  useEffect(() => { Promise.resolve().then(refresh) }, [])
  useEffect(() => { if (selected) getWorkerComplaint(selected).then(setDetail).catch(e => setError(e.message)) }, [selected])
  async function update(task, status) {
    setSaving(true); setError('')
    try { await updateWorkerTask(task.id, { status, note: note.trim() || null }); setNote(''); await refresh(); if (selected) setDetail(await getWorkerComplaint(selected)) }
    catch (e) { setError(e.message) } finally { setSaving(false) }
  }
  const pending = tasks.filter(t => t.status === 'ASSIGNED').length
  const active = tasks.filter(t => t.status === 'IN_PROGRESS').length
  const done = tasks.filter(t => t.status === 'COMPLETED').length
  return <div className="warden-app"><header className="warden-topbar"><a className="warden-brand" href="/worker/dashboard"><span className="warden-brand-mark">H</span><span>HostelDesk<small>WORKER PORTAL</small></span></a><div className="warden-user"><span className="warden-avatar">{profile.name.slice(0,1).toUpperCase()}</span><span>{profile.name}<small>{profile.email}</small></span><button className="student-link" onClick={onSignOut}>Sign out</button></div></header>
    <main className="warden-main"><PageTitle title="My assigned work" subtitle="Tasks assigned to you by the hostel Warden." />
      <div className="warden-metrics"><Metric label="Pending" value={pending} tone="amber"/><Metric label="In progress" value={active} tone="blue"/><Metric label="Completed" value={done} tone="green"/></div>
      {error && <p className="warden-error" role="alert">{error}</p>}
      {!selected && (loading ? <p className="warden-state" role="status">Loading assigned work…</p> : !tasks.length ? <section className="warden-card"><p className="warden-state">No work has been assigned to you yet.</p></section> : <section className="warden-card"><h2>Assigned complaints</h2><div className="warden-table-wrap"><table className="warden-table"><thead><tr><th>Complaint</th><th>Location</th><th>Priority</th><th>Status</th><th /></tr></thead><tbody>{tasks.map(task => <tr key={task.id}><td><strong>#{task.complaint_id}</strong><span className="warden-truncate">{task.description}</span></td><td>Block {task.block}, Room {task.room}</td><td>{human(task.severity)}</td><td>{human(task.status)}</td><td><button className="button button--secondary" onClick={() => openComplaint(task.complaint_id)}>Open</button></td></tr>)}</tbody></table></div></section>)}
      {selected && !detail && <p className="warden-state" role="status">Loading complaint…</p>}
      {detail && <section className="warden-card worker-detail"><button className="warden-back" onClick={closeComplaint}>← Back to assigned work</button><PageTitle title={`Complaint #${detail.id}`} subtitle={`Submitted ${new Date(detail.created_at).toLocaleString()}`} /><span className="warden-badge">{human(detail.status)}</span><p className="complaint-description">{detail.description}</p><dl className="warden-details"><div><dt>Location</dt><dd>Block {detail.block}, Room {detail.room}</dd></div><div><dt>Category</dt><dd>{human(detail.category)}</dd></div><div><dt>Priority</dt><dd>{human(detail.severity)}</dd></div></dl>{detail.worker_note && <p>Completion note: {detail.worker_note}</p>}
        {tasks.find(t => t.complaint_id === detail.id)?.status !== 'COMPLETED' && <div className="worker-actions">{tasks.find(t => t.complaint_id === detail.id)?.status === 'ASSIGNED' && <button className="button button--primary" disabled={saving} onClick={() => update(tasks.find(t => t.complaint_id === detail.id), 'IN_PROGRESS')}>{saving ? 'Saving…' : 'Start work'}</button>}<label>Completion note<textarea rows="3" maxLength="1000" value={note} onChange={e => setNote(e.target.value)} placeholder="Add a brief note when the work is complete" /></label><button className="button button--primary" disabled={saving || tasks.find(t => t.complaint_id === detail.id)?.status === 'ASSIGNED'} onClick={() => update(tasks.find(t => t.complaint_id === detail.id), 'COMPLETED')}>{saving ? 'Saving…' : 'Mark completed'}</button></div>}
      </section>}
    </main></div>
}
function PageTitle({ title, subtitle }) { return <header className="warden-page-title"><div><p className="warden-kicker">Maintenance work</p><h1>{title}</h1><p>{subtitle}</p></div></header> }
function Metric({ label, value, tone }) { return <article className={`warden-metric ${tone}`}><span>{label}</span><strong>{value}</strong></article> }
export default function WorkerApp() { return <RoleGate role="worker" dashboard={<WorkerWorkspace />} /> }
