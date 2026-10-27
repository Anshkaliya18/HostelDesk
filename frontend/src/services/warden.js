const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
import { supabase } from './supabase.js'
import { track } from '../utils/coldStart.js'

async function request(path, options = {}) {
  const { data: { session } = {} } = supabase ? await supabase.auth.getSession() : {}
  if (!session?.access_token) throw new Error('Your Warden session has ended. Sign in again.')
  const response = await track(fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { Accept: 'application/json', Authorization: `Bearer ${session.access_token}`, ...options.headers },
  }))
  if (!response.ok) {
    if (response.status === 401) {
      await supabase?.auth.signOut()
      throw new Error('Your Warden session expired. Sign in again.')
    }
    let message = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch { /* Keep the status message for non-JSON errors. */ }
    throw new Error(message)
  }
  return response.json()
}

export const getDashboard = () => request('/warden/dashboard')
export const getWorkers = () => request('/warden/workers')
export const getReports = () => request('/warden/reports')
export const getComplaint = id => request(`/complaints/${id}`)
export const getPhoto = async id => {
  const { data: { session } = {} } = supabase ? await supabase.auth.getSession() : {}
  if (!session?.access_token) throw new Error('Your Warden session has ended. Sign in again.')
  const response = await fetch(`${API_BASE_URL}/complaints/${id}/photo`, {
    headers: { Accept: 'image/*', Authorization: `Bearer ${session.access_token}` },
  })
  if (response.status === 401) {
    await supabase?.auth.signOut()
    throw new Error('Your Warden session expired. Sign in again.')
  }
  if (!response.ok) return null
  return URL.createObjectURL(await response.blob())
}
export const getComplaints = filters => {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value !== false))
  return request(`/complaints${query.size ? `?${query}` : ''}`)
}
export const reviewComplaint = (id, payload) => request(`/complaints/${id}/review`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
})
export const reanalyzeComplaint = id => request(`/complaints/${id}/reanalyze`, { method: 'POST' })
export const aiSweep = () => request('/warden/ai-sweep', { method: 'POST' }).catch(() => null)
export const getAlerts = () => request('/alerts')
export const getDigest = day => {
  const query = day ? `?date=${encodeURIComponent(day)}` : ''
  return request(`/digest${query}`)
}
