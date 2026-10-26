const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
// Demo auth contract: the backend resolves the user from the X-User-Id header
// (see backend/app/core/security.py). The seeded demo student is id 1,
// overridable without code changes via VITE_DEMO_STUDENT_ID.
const DEMO_STUDENT_ID = String(import.meta.env.VITE_DEMO_STUDENT_ID ?? '1')
// The backend persists the complaint row immediately, then uploads the photo
// and runs the Gemma analysis inside this same request, so the client must
// wait far longer than a plain CRUD call.
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
 * Authentication: the backend demo contract resolves the student from the
 * ``X-User-Id`` header. The browser must NOT set Content-Type manually -
 * fetch generates the multipart boundary itself.
 */
export async function submitComplaint({ description, block, room, photo }) {
  const formData = new FormData()
  formData.append('description', description)
  formData.append('block', block)
  formData.append('room', room)
  if (photo) formData.append('photo', photo, photo.name)

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}/complaints`, {
      method: 'POST',
      body: formData,
      headers: { Accept: 'application/json', 'X-User-Id': DEMO_STUDENT_ID },
      signal: controller.signal,
    })

    if (!response.ok) {
      let fallback = `Complaint request failed with status ${response.status}.`
      let message = fallback
      try {
        message = extractBackendDetail(await response.json(), fallback)
      } catch {
        // Non-JSON error body: keep the status-based message.
      }
      throw new Error(message)
    }

    let payload = null
    try {
      payload = await response.json()
    } catch {
      // A successful 204/empty response is valid; no reference is available.
    }

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
