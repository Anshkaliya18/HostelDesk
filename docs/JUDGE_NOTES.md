# Judge notes — HostelDesk

Fast orientation for reviewing and stress-testing HostelDesk. The one-sentence
pitch: **an AI-assisted hostel complaint desk where the AI suggests and people
decide.**

Live site: <https://hosteldesk.aurio.workers.dev> · API: <https://hosteldesk-qgx8.onrender.com>

| Role | Email | Password |
| --- | --- | --- |
| Student | `demo.student@hosteldesk.dev` | `DemoStudent2026!` |
| Warden | `demo.warden@hosteldesk.dev` | `DemoWarden2026!` |
| Worker | `demo.worker@hosteldesk.dev` | `DemoWorker2026!` |

## Why AI, and why only as a suggestion?

Hostel complaints arrive as one photo plus a one-line, often ambiguous note
("fan not working", written in English, Hindi, or Hinglish). A small on-call
warden team has to decide, for each note: what trade handles it, how urgent it
is, whether it is the same problem reported twice. Classification is exactly
the kind of narrow, bounded task a vision model does well — so the backend
sends the photo + description (+ up to 5 recent open complaints in the same
block for duplicate hints) to **Gemini 2.5 Flash** and stores a
*recommendation*: category, severity, suggested trade, confidence, a ≤20-word
reason, a safety flag, and a possible duplicate id.

Decision-making stays human on purpose: the AI cannot assign a worker, change
a complaint's owner, or close anything. It writes one recommendation row; a
warden button-press is required before a task exists, and the student must
confirm "Yes, fixed" (or reopen) before the loop counts as closed. The warden
also sees a **Re-run AI** button when a first pass produced nothing usable, so
the model failing is never a dead end.

## Why not a WhatsApp bot?

The valuable, verifiable part of the workflow is the *state machine* —
submitted → analyzed → reviewed → assigned → in-progress → completed — with
role-scoped privacy (RLS row-level security), photo evidence in a private
bucket, an audit history, and a digest. A chat thread cannot enforce that loop
and is nearly impossible to demo cleanly in two minutes. WhatsApp integration
is a natural future *notification* layer (the digest already exports
WhatsApp-ready plain text), but we kept the core in one place we can test.

## What happens if the AI is wrong, slow, or down?

- **Malformed / invalid output:** the recommendation row stores the failure;
  the complaint still moves to `WARDEN_REVIEW` with an "AI unavailable" note.
  Output validation drops nonsense: an invented duplicate id the model was
  never shown, an out-of-vocabulary trade, or an over-long reason.
- **Safety:** if the model flags exposed wiring, flooding, fire risk, etc.,
  severity is force-escalated to HIGH with a red "Safety risk" badge.
- **Timeouts:** one bounded retry per model, then the fallback model
  (`gemini-2.5-flash-lite`); the student never waits — analysis runs in the
  background after the 201 response.
- **A background sweep:** if a complaint sits in `SUBMITTED` for over 2
  minutes without a recommendation, the warden dashboard/queue kicks a bounded
  sweep (max 5 complaints) to re-attempt analysis.

## What about fake complaints, a confused model, or spam?

- Rate limits: 5 complaints per 10 minutes and 20 per day per student; 10
  signups per hour per IP; staff signup additionally needs a server-side
  invite code.
- Warden and Worker signup share `STAFF_INVITE_CODE`; it belongs in the
  backend environment only, never in frontend variables or committed docs.
  A wrong code is still a signup attempt and counts toward the per-IP limit.
- The signup limiter is in-memory per API process. Restarting the local API
  clears its local counter; hosted Supabase Auth limits are separate.
- The model is anchored with a strict prompt ("answer only from the photo,
  text, and recent list; never invent problems") and a forced JSON schema.
- Duplicate hints are advisory — the warden judge them; a confirmed duplicate
  still needs a human decision.
- Every mutation is authenticated (Supabase bearer token) and RLS-enforced in
  Postgres; SQLite-local tests exercise the same service layer.

## Current portal UI

- **Warden complaint queue:** status, category, priority, block, review-needed,
  and sort filters; debounced search; result count; removable filter chips; and
  a keyboard-accessible Review action on every row.
- **Warden complaint review:** report details and history sit alongside the
  advisory AI recommendation and explicit worker assignment/review controls.
  The review panel moves below the report on narrow screens.
- **Warden reports:** choose a UTC report date, inspect deterministic daily
  counts and category/hotspot/oldest-open views, then copy or download the
  digest as plain text.
- **Worker dashboard:** open, to-start, completed, and all-task filters;
  assignment counts; task detail/history; and a required completion note.
  Warden and Worker pages share a lazily loaded portal stylesheet so direct
  Worker navigation receives the same responsive layout.

For local staff signup, set `STAFF_INVITE_CODE` in `backend/.env` and restart
FastAPI after changing it. Use that same value in either the Warden or Worker
signup form. Never commit the active invite code; set a separate secret in the
hosting provider for deployment.

## Student confirmation: why the loop

The status chain ends at COMPLETED, but "completed" is a claim by staff. The
student gets a task-like confirmation: "Yes, fixed" (history note recorded,
status stays COMPLETED) or "Not fixed" with a 5–300 character reason, which
reopens the complaint into `WARDEN_REVIEW` for a fresh warden decision. This
closes the accountability loop without giving students write access to
anything except their own complaint's confirm/reopen.

## Scaling notes

- Everything is stateless apart from the in-memory rate-limit/cache windows;
  Postgres + FastAPI+uvicorn workers scale horizontally once limits move to
  Redis (documented limitation).
- Photos live in a private Supabase Storage bucket; the DB keeps only the key
  and generates short-lived signed URLs.
- Migrations are additive and reversible (Alembic up/down tested); the app
  role is a non-owner with request-scoped policies.

## Why Gemini 2.5 Flash instead of Gemma 4

The AI integration never hard-codes a model: `GEMINI_MODEL` /
`GEMINI_FALLBACK_MODEL` environment variables choose whatever model is
addressable through the server-side Generative Language API, and the code
adapts its request shape per family (strict JSON `responseSchema` +
disabled thinking budget for Gemini 2.5; free-form JSON text for Gemma-style
models). Google does not currently expose Gemma 4 through usable AI-Studio
keys, so the shippable default is **Gemini 2.5 Flash** with
`gemini-2.5-flash-lite` fallback; the day Gemma 4 is API-addressable, the
swap is `GEMINI_MODEL=gemma-4-31b-it` plus one deployment restart.

The docs (screen deck and older files) may still mention Gemma 4; the
authoritative, always-current statement of what actually runs is this file
plus `GET /health/ai` on the API, which reports the live model, fallback,
timeout and duplicate-check configuration without exposing any secret.
