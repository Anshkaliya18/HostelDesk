import { API_BASE_URL, readApiJson } from './apiBase.js'
// The backend persists the complaint row immediately, then classifies and
// stores the photo while the AI analysis runs in the background, so the
// client must allow far longer than a plain CRUD call.
import { track } from '../utils/coldStart.js'
const REQUEST_TIMEOUT_MS = 120_000

function extractReference(payload) {
  const record = payload?.data ?? payload?.complaint ?? payload
  const reference =
    record?.reference ?? record?.complaint_reference ?? record?.complaint_id ?? record?.id

  if (reference === null || reference === undefined || reference === '') return null
  return String(reference)
}

function extractBackendDetail(body, fallback) {
  if (!body?.detail) return fallback
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail)) {
    const first = body.detail[0]
    if (first?.msg) return first.msg
  }
  return fallback
}

/**
 * Sends a complaint to POST /complaints as multipart form data with fields
 * matching the FastAPI endpoint exactly:
 *   description: str = Form(...)
 *   block:       str = Form(...)
 *   room:        str = Form(...)
 *   photo:       UploadFile | None = File(None)
 *
 * Authentication: the backend verifies the Supabase bearer token and loads
 * the linked Student profile. The browser must NOT set Content-Type manually;
 * fetch generates the multipart boundary itself.
 */
export async function submitComplaint({ description, block, room, photo, accessToken }) {
  if (!accessToken) throw new Error('Sign in as a Student before submitting a complaint.')
  const formData = new FormData()
  formData.append('description', description)
  formData.append('block', block)
  formData.append('room', room)
  if (photo) formData.append('photo', photo, photo.name)

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await track(fetch(`${API_BASE_URL}/complaints`, {
      method: 'POST',
      body: formData,
      headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    }))

    if (!response.ok) {
      let fallback = `Complaint request failed with status ${response.status}.`
      let message = fallback
      try {
        message = extractBackendDetail(await readApiJson(response), fallback)
      } catch {
        // Non-JSON error body: keep the status-based message.
      }
      throw new Error(message)
    }

    const payload = response.status === 204 ? null : await readApiJson(response)

    const record = payload?.data ?? payload ?? {}
    return { reference: extractReference(payload), status: record.status ?? null, isPreview: false }
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('The complaint request timed out.', { cause: error })
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
}

/**
 * Student "My complaints": list, detail, confirm, reopen.
 * All endpoints require the Supabase bearer token; errors surface the
 * backend `detail` message (including the rate-limit and state-guard text).
 */
async function authedRequest(path, { method = 'GET', body, accessToken } = {}) {
  if (!accessToken) throw new Error('Sign in as a Student to track your complaints.')
  const response = await track(fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${accessToken}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  }))
  if (!response.ok) {
    let fallback = `Request failed with status ${response.status}.`
    let message = fallback
    try {
      message = extractBackendDetail(await readApiJson(response), fallback)
    } catch {
      // Non-JSON error body: keep the status-based message.
    }
    throw new Error(message)
  }
  try {
    return await readApiJson(response)
  } catch {
    return null
  }
}

export const fetchMyComplaints = accessToken => authedRequest('/complaints/mine', { accessToken })
export const fetchComplaint = (id, accessToken) => authedRequest(`/complaints/${id}`, { accessToken })
export const confirmComplaint = (id, accessToken) =>
  authedRequest(`/complaints/${id}/confirm`, { method: 'POST', accessToken })
export const reopenComplaint = (id, reason, accessToken) =>
  authedRequest(`/complaints/${id}/reopen`, { method: 'POST', body: { reason }, accessToken })
