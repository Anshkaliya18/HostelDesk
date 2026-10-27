import { useSyncExternalStore } from 'react'
import { getSnapshot, subscribe } from '../utils/coldStart.js'

/** Small fixed notice shown while an API request exceeds 4 seconds
 * (free-tier cold start), in place of a frozen blank state. */
export default function ColdStartBanner() {
  const slow = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  if (!slow) return null
  return (
    <div className="cold-start-banner" role="status" aria-live="polite">
      Waking up the server, one moment…
    </div>
  )
}
