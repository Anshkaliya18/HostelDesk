const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
const USE_LOCAL_PREVIEW = import.meta.env.DEV && !API_BASE_URL
const REQUEST_TIMEOUT_MS = 20_000

function createPreviewReference() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const values = new Uint8Array(4)

  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(values)
  } else {
    for (let index = 0; index < values.length; index += 1) {
      values[index] = Math.floor(Math.random() * 256)
    }
  }

  const suffix = Array.from(values, (value) => alphabet[value % alphabet.length]).join('')
  return `HD-L-${suffix}`
}

function wait(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds)
  })
}

function extractReference(payload) {
  const record = payload?.data ?? payload?.complaint ?? payload
  const reference =
    record?.reference ?? record?.complaint_reference ?? record?.complaint_id ?? record?.id

  if (reference === null || reference === undefined || reference === '') return null
  return String(reference)
}

/**
 * Sends a complaint to POST /complaints as multipart form data.
 *
 * The FastAPI endpoint can read:
 *   description: str = Form(...)
 *   room: str = Form(...)
 *   photo: UploadFile | None = File(None)
 *
 * Set VITE_API_BASE_URL to the API origin (for example
 * http://localhost:8000) to connect the real service. Until then, dev mode
 * uses an isolated local preview so the complete UI can be reviewed.
 */
export async function submitComplaint({ description, room, photo }) {
  const formData = new FormData()
  formData.append('description', description)
  formData.append('room', room)
  if (photo) formData.append('photo', photo, photo.name)

  if (USE_LOCAL_PREVIEW) {
    await wait(700)
    return { reference: createPreviewReference(), isPreview: true }
  }

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}/complaints`, {
      method: 'POST',
      body: formData,
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`Complaint request failed with status ${response.status}.`)
    }

    let payload = null
    try {
      payload = await response.json()
    } catch {
      // A successful 204/empty response is valid; no reference is available.
    }

    return { reference: extractReference(payload), isPreview: false }
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('The complaint request timed out.', { cause: error })
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
}
