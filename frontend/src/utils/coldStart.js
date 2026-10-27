/**
 * Cold-start monitor for the free-tier API hosting.
 *
 * On app load it fires a fire-and-forget GET /health ping. Every backend
 * request made through the shared service helpers is tracked: if any request
 * is still unresolved after 4 seconds (Render free tier cold start can take
 * ~50s), the UI may show a small "Waking up the server…" notice instead of a
 * frozen blank state. The notice clears automatically once requests land.
 */

const SLOW_AFTER_MS = 4000

let slowCount = 0
let slow = false
const listeners = new Set()

function setSlow(next) {
  if (slow !== next) {
    slow = next
    for (const listener of listeners) listener(next)
  }
}

export function track(promise) {
  if (!promise || typeof promise.then !== 'function') return promise
  let timedOut = false
  let settled = false
  const timer = window.setTimeout(() => {
    timedOut = true
    slowCount += 1
    setSlow(true)
  }, SLOW_AFTER_MS)
  function done() {
    if (settled) return
    settled = true
    window.clearTimeout(timer)
    if (timedOut) slowCount = Math.max(0, slowCount - 1)
    if (slowCount === 0) setSlow(false)
  }
  promise.then(done, () => {})
  return promise
}

/** Fire-and-forget one-time health ping so the cold start clock starts early. */
export function warmUp(apiBaseUrl) {
  try {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 12_000)
    track(
      fetch(`${apiBaseUrl}/health`, { signal: controller.signal })
        .catch(() => {})
        .finally(() => window.clearTimeout(timer)),
    )
  } catch {
    // Never let the warm-up itself break the app.
  }
}

export function subscribe(listener) {
  listeners.add(listener)
  listener(slow)
  return () => listeners.delete(listener)
}

export const getSnapshot = () => slow
