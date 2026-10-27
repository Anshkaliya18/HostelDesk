const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
import { supabase } from './supabase.js'
import { track } from '../utils/coldStart.js'

async function request(path, options = {}, tokenOverride) {
  const { data: { session } = {} } = supabase ? await supabase.auth.getSession() : {}
  const token = tokenOverride || session?.access_token
  if (!token) throw new Error('Your session has ended. Sign in again.')
  const response = await track(fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...options.headers },
  }))
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail }
    catch { /* retain status fallback */ }
    throw new Error(message)
  }
  return response.json()
}

async function signup(path, payload) {
  const response = await track(fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  if (!response.ok) {
    let message = `Signup failed (${response.status}).`
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail }
    catch { /* retain status fallback */ }
    throw new Error(message)
  }
  return response.json()
}

export const getRoleProfile = token => request('/auth/me', {}, token)
export const signupStudent = payload => signup('/auth/student/signup', payload)
export const signupWarden = payload => signup('/auth/warden/signup', payload)
export const signupWorker = payload => signup('/auth/worker/signup', payload)
export const getWorkerTasks = () => request('/tasks/my')
export const getWorkerComplaint = id => request(`/complaints/${id}`)
export const updateWorkerTask = (id, payload) => request(`/tasks/${id}/status`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
})
