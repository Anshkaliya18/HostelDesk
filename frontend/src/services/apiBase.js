const productionApiOrigin = 'https://hosteldesk-qgx8.onrender.com'
const configuredApiOrigin = (import.meta.env.VITE_API_BASE_URL || '').trim()

// Local development uses Vite's /auth, /complaints, etc. proxy. Production
// must call the FastAPI service directly instead of the static SPA Worker.
export const API_BASE_URL = (
  configuredApiOrigin || (import.meta.env.PROD ? productionApiOrigin : '')
).replace(/\/+$/, '')

export async function readApiJson(response) {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.toLowerCase().includes('json')) {
    const body = await response.text()
    if (/^\s*(?:<!doctype\s+html|<html\b)/i.test(body)) {
      const origin = response.url ? new URL(response.url).origin : 'the configured API origin'
      throw new Error(`The API returned an HTML page from ${origin}. Check VITE_API_BASE_URL and point it to the FastAPI backend.`)
    }
    throw new Error('The API returned a non-JSON response.')
  }
  return response.json()
}
