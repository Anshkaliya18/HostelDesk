# HostelDesk

> **AI-assisted hostel complaint & maintenance desk — AI suggests, the Warden decides.**

**Live Demo → https://hosteldesk.aurio.workers.dev**

| Deployment | URL | Status |
| --- | --- | --- |
| **Frontend (Student / Warden / Worker portals)** | [hosteldesk.aurio.workers.dev](https://hosteldesk.aurio.workers.dev/) | Live on Cloudflare Workers |
| **Backend API (FastAPI)** | [hosteldesk-qgx8.onrender.com](https://hosteldesk-qgx8.onrender.com/) | Live on Render |
| **API Docs (Swagger)** | [hosteldesk-qgx8.onrender.com/docs](https://hosteldesk-qgx8.onrender.com/docs) | Live |
| **Database & Auth & Storage** | Supabase (PostgreSQL + Auth + private Storage bucket) | Live |

---

## What it does

HostelDesk turns a hostel complaint **photo + one-line note** into a structured, trackable maintenance task:

1. A **Student** uploads a photo of the problem (broken fan, leaking tap·) with a short note
2. **AI** analyzes the photo + text and suggests a **category**, **severity**, and **worker type**
3. The **Warden** reviews the AI recommendation, edits if needed, and approves → a task is created .
4. The assigned **Worker** picks up the task, marks it in-progress, completes it with a note .
5. The **Student** sees live status updates end-to-end

The warden also gets **repeat-problem alerts** and a **daily digest** — no AI required for those, just deterministic rules.

> ### The core principle
> **AI suggests; the Warden decides.** The model never assigns a worker or decides about students — the warden's review creates the task.

---

## Key Features

### Student Portal
- Photo upload (client-side validated, downsized to ≤1600px, re-encoded JPEG, metadata stripped)
- One-line complaint description + block/room
- **"My complaints" tracking**: live status timeline auto-refreshes while a complaint is open
- Complaint completion is confirmed by the student — **"Yes, fixed"** or **reopen with a reason** (the warden re-reviews)
- Duplicate-block suggestions and rate limits protect the queue from spam

### Warden Portal
- Complaint queue with filters (status / category / severity / search / block / sort), result counts, removable active-filter chips, and a debounced search
- Keyboard-accessible complaint review actions, distinct priority/status badges, and a responsive review layout
- **Needs-review quick filter + "oldest unreviewed first" sort**
- AI-generated category, severity & suggested worker, with **reason, confidence, and repeat-complaint flags**
- **Approve AI suggestion** (one click — the warden still presses the button) or edit any field
- Matching-trade workers listed first, sorted by fewest active tasks; **Re-run AI** when a first pass failed
- Red **Safety risk** badge whenever the AI flags a hazard (auto-escalates severity to HIGH)
- Repeat-problem alerts (deterministic rule: same block + category recurring complaints) — clickable through to the filtered queue, with an explicit warden-only "Mark resolved" action (server-set timestamp; resolving lets a genuine recurrence raise a fresh alert)
- Daily digest report with a UTC date selector, deterministic counters, category mix, hotspots, oldest open complaint, and active alerts
- Copy or download a plain-text digest to share with the hostel team

### Worker Portal
- Responsive assignment dashboard with counts and Open / To start / Completed / All queue filters
- Complaint detail, location, priority, assignment time, and progress history
- ASSIGNED → IN_PROGRESS → COMPLETED workflow with a completion note required to close a job
- Worker and Warden portals load as separate frontend chunks and share the portal stylesheet

### AI Engine (Gemini 2.5, server-side only)
- Default model `gemini-2.5-flash` with `gemini-2.5-flash-lite` fallback (thinking budget disabled, strict JSON response schema; Gemma 4 remains a one-line config swap)
- Categories: **Electrical · Plumbing · Cleaning · Furniture**
- Severity: **Low · Medium · High**
- Worker suggestions: **Electrician · Plumber · Cleaner · Carpenter**
- Graceful fallback: if AI is unavailable, the complaint lands directly in `WARDEN_REVIEW` for manual categorization — the flow never blocks

---

## Complaint Lifecycle

```text
SUBMITTED → AI_ANALYZED → WARDEN_REVIEW → ASSIGNED → IN_PROGRESS → COMPLETED
```

---

## Architecture
.
```text
              https://hosteldesk.aurio.workers.dev
              Student  ·  Warden  ·  Worker (React SPA)
                            ” HTTPS
                            –
              https://hosteldesk-qgx8.onrender.com
              FastAPI (auth, complaints, tasks, digest)
               ”            ”              ”
               –            –              –
      Supabase Auth   Supabase Postgres   Gemini API (2.5 Flash)
      (email+token)   (RLS-protected)     (classification)
               ”            ”
               –            –
      Private Storage  Alembic migrations
      (complaint photos)
```

**Security model:**
- Photos are stored in a **private** Supabase Storage bucket; the DB keeps only the storage key
- The **service-role key never leaves the backend** — the browser only uses the public publishable key
- Row-Level Security policies on every table; a dedicated non-owner `hosteldesk_app` DB role runs the API
- All AI calls happen server-side; no AI keys in frontend code

---

## Tech Stack

| Layer | Tech |
| --- | --- |
| Frontend | React 19 · Vite · plain CSS |
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.x · Pydantic v2 · Alembic |
| Database | Supabase PostgreSQL (with RLS) |
| Auth | Supabase Auth (role-based signup: Student / Warden / Worker) |
| Storage | Supabase Storage — private `complaint-photos` bucket |
| AI | Gemini API (server-side REST, env-configurable model — `gemini-2.5-flash` in production) |
| Hosting | Cloudflare Workers (frontend static assets) · Render (backend) |
| Tests | pytest — 113 backend tests |

---

## Try the live demo

**Sign up directly on the live site** — Student registration is a single step (choose a role → name, email, password → dashboard opens). No email confirmation needed. Warden/Worker signups additionally require the staff invite code configured on the server (judges can simply use the demo accounts below).

**Local judge signup test code:** `HOSTELDESK-JUDGE-LOCAL-ONLY`. This sample is for a local backend only. Set `STAFF_INVITE_CODE=HOSTELDESK-JUDGE-LOCAL-ONLY` in `backend/.env`, leave `WARDEN_SIGNUP_CODE` and `WORKER_SIGNUP_CODE` blank, and restart FastAPI. Role-specific codes override the shared code. This sample is not a production invite; live invite codes remain private in the hosting environment.

Suggested demo walkthrough (one complaint, all three roles):

```text
1. Sign in as Student      → submit a photo of a broken fan + a short note
2. Student                 → "My complaints": watch the status timeline update live
3. Sign in as Warden       → the complaint arrives AI-tagged (ELECTRICAL / HIGH / Electrician)
                             with reason + confidence → "Approve AI suggestion"
4. Sign in as Worker       → electrician sees the task → Start work → Complete (note required)
5. Back in the Student tab → COMPLETED → "Track this complaint" → "Yes, fixed"
                             (or "Not fixed" with a reason — the warden re-reviews)
6. Warden → Reports        → repeat-problem alerts, hotspots, daily digest + "Copy digest"
```

> Tip: open the three roles in separate browser tabs/incognito windows for the smoothest demo..

**Demo accounts on the live site** (also usable by judges):

| Role | Email | Password |
| --- | --- | --- |
| Student | `demo.student@hosteldesk.dev` | `DemoStudent2026!` |
| Warden | `demo.warden@hosteldesk.dev` | `DemoWarden2026!` |
| Worker | `demo.worker@hosteldesk.dev` | `DemoWorker2026!` |

---

## Screenshots (from the live deployment)

### Student portal .

| Login | Complaint submitted with photo |
| --- | --- |
| <img src="docs/screenshots/01-student-login.png" width="420" alt="Student login"> | <img src="docs/screenshots/02-student-complaint-success.png" width="420" alt="Complaint submitted success screen"> |

### Warden portal

| Overview | Complaint queue with filters |
| --- | --- |
| <img src="docs/screenshots/03-warden-dashboard.png" width="420" alt="Warden overview dashboard"> | <img src="docs/screenshots/04-warden-queue.png" width="420" alt="Complaint queue with filters"> |

| Review gate | Reports and insights |
| --- | --- |
| <img src="docs/screenshots/05-warden-review.png" width="420" alt="Review gate - photo, status history, AI recommendation, assignment"> | <img src="docs/screenshots/06-warden-reports.png" width="420" alt="Reports and insights"> |

<p align="center">
  <img src="docs/screenshots/07-warden-workers.png" width="420" alt="Workers availability">
</p>

### Worker portal

| Dashboard | Assigned tasks |
| --- | --- |
| <img src="docs/screenshots/08-worker-dashboard.png" width="420" alt="Worker dashboard"> | <img src="docs/screenshots/09-worker-tasks.png" width="420" alt="Assigned tasks"> |

| Task detail | Completed with note |
| --- | --- |
| <img src="docs/screenshots/10-worker-task-detail.png" width="420" alt="Task detail"> | <img src="docs/screenshots/11-worker-completed.png" width="420" alt="Completed task with completion note"> |

---

## Project Structure
.
```text
HostelDesk/
”
””·”· frontend/            # React app (all three role portals)
”   ””·”· src/pages/       #   Student / Warden / Worker screens
”   ””·”· src/services/    #   Supabase + API clients
”   ””·”· wrangler.jsonc   #   Cloudflare Workers static-assets deploy
”   ”””·”· .env.example     #   Vite build-time environment template
”
””·”· backend/             # FastAPI service
”   ””·”· app/             #   routes, services, schemas, db, core
”   ””·”· alembic/         #   DB migrations (incl. RLS policy migration)
”   ””·”· tests/           #   113 pytest tests
”   ””·”· seed.py          #   demo data seeder (empty-DB seeding)
”   ””·”· scripts/seed_demo.py   # judge-ready demo dataset + photos (see below)
”   ”””·”· .env.example     #   full backend environment template
”
””·”· docs/screenshots/    # live-deployment screenshots used above
””·”· Readme.md            # this file
”””·”· LICENSE              # MIT
```

---

## Run it locally

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # then fill in your keys (see below)

# Optional: for local judge signup testing only, use the documented
# HOSTELDESK-JUDGE-LOCAL-ONLY code; keep role-specific codes blank.
# For your own local invite instead, generate one with:
# python -c "import secrets; print('HD-' + secrets.token_urlsafe(18))"

python -m alembic upgrade head      # create tables
python seed.py                      # optional base demo data
.venv\Scripts\python.exe scripts\seed_demo.py   # judge-ready demo dataset + photos (demo_assets/)
uvicorn app.main:app --reload --port 8000
```

Swagger UI: <http://127.0.0.1:8000/docs>

> Without `GEMINI_API_KEY` or Supabase keys the app still runs: AI is skipped (complaints go straight to warden review) and photos fall back to the local `uploads/` folder.

### 2. Frontend (Vite) :

```bash
cd frontend
npm install
copy .env.example .env.local        # then fill in the three VITE_ vars
npm run dev
```

The dev proxy forwards API calls to `127.0.0.1:8000`.

---

## Environment Variables

Full templates with comments live in [`backend/.env.example`](backend/.env.example) and [`frontend/.env.example`](frontend/.env.example).

**Backend (`backend/.env`) — essentials:**

```env
DATABASE_URL=postgresql+psycopg2://<role>:<password>@<host>:5432/postgres
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side only — never in the browser>
GEMINI_API_KEY=<google ai studio key>
WARDEN_SIGNUP_CODE=<private-warden-invite>
WORKER_SIGNUP_CODE=<private-worker-invite>
# Optional shared fallback when a role-specific code is not set:
STAFF_INVITE_CODE=<private-shared-invite>
CORS_ORIGINS=http://localhost:5173,https://hosteldesk.aurio.workers.dev
```

Model names, rate limits (complaints + signups) and severity SLAs all have sensible defaults and can be overridden — see the commented template.
The signup limit defaults to 10 attempts per hour per client IP and is held in memory by the API process. During local development, restarting FastAPI clears that process-local counter. It does not reset any separate Supabase Auth limits. Staff codes are checked by the backend: `WARDEN_SIGNUP_CODE` and `WORKER_SIGNUP_CODE` allow separate invite codes and each overrides the optional shared `STAFF_INVITE_CODE` fallback. If no applicable code is set, signup for that staff role returns 403. Students can still sign up without a code.

**Production staff signup:** the Render backend service must have the appropriate role-specific code set under **Environment** and must be redeployed after changing it. The deployed backend reads these values directly from its environment:

```python
warden_code = settings.warden_signup_code or settings.staff_invite_code
worker_code = settings.worker_signup_code or settings.staff_invite_code
```

The role-specific production variables are honored by the current backend. Keep real invite values in Render's secret environment only; share the relevant code directly with the intended Warden or Worker. Never commit real codes to this documentation or the repository.

**Frontend (`frontend/.env.local`) — all three build-time vars are required:**

```env
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<public publishable key>
VITE_API_BASE_URL=https://hosteldesk-qgx8.onrender.com
```

> **Never** commit real `.env` files, put the service-role key in frontend code, or upload real student records.

---

## Deployment (how this repo is hosted)

- **Frontend → Cloudflare Workers** (static assets, SPA fallback so `/warden/*` routes survive refresh):
  ```bash
  cd frontend
  npm run build
  npx wrangler deploy
  ```
- **Backend → Render**: FastAPI web service; set the env vars above in the Render dashboard (note `CORS_ORIGINS` must include the exact Cloudflare frontend origin).
- **Database/Auth/Storage → Supabase**: run Alembic migrations with the migration connection string, create the private `complaint-photos` bucket.

---

## Tests

```bash
cd backend
python -m pytest -q
```

118 tests cover AI readiness (including malformed output, duplicate-check prompts, the Gemini 2.5 request shape), complaint validation & ownership, role-based auth, staff invite codes, rate limits, the student confirm/reopen loop, warden dashboard/filters (including block + needs-review), worker task ownership, the warden review gate, repeat-problem alerts (incl. submission-time detection and the explicit warden resolve lifecycle), digest + severity-based SLA, safe handling of invalid AI output, storage (validation, safe filenames, signed URLs), FK integrity, and Alembic upgrade/downgrade reproducibility.

---

## MVP Scope & What's Next

**In the MVP:** student submission with photo, AI classification (photo + text), warden review gate, worker assignment & completion, student status tracking, repeat-problem alerts, daily digest.

**Future work:** push notifications · mobile app · hostel entry/exit · mess · attendance · fee management.

---

## Branches

This repo was built with separate workstream branches, now merged into `main`:

| Branch | Focus |
| --- | --- |
| `main` | integrated MVP (current) |
| `feature/student` | student UI + complaint flow |
| `feature/warden-ai` | AI integration + warden dashboard |
| `feature/backend-worker` | backend, database, worker workflow, insights |

---

## For judges

**The one-sentence version:** HostelDesk is an AI-assisted hostel complaint desk where **the AI suggests and people decide** — a warden explicitly approves every assignment, a student explicitly confirms every fix.

**Model:** the backend calls Google's **Gemini 2.5 Flash** through the server-side Generative Language REST API, with `gemini-2.5-flash-lite` as an automatic fallback. Thinking budget is disabled and the reply is forced to a strict JSON schema, so classification is fast and structurally validated. Gemma-only deployments remain a one-line config swap (`GEMINI_MODEL`) once API-side Gemma 4 access is available.

**"AI suggests, people decide" is enforced in code, not copy:**
- The AI only ever writes a *recommendation row* (category / severity / trade / reason / confidence / possible duplicate). It cannot assign workers, change ownership, or close complaints.
- A warden must press a button that submits their own review before any task exists.
- A student must confirm "Yes, fixed" before the loop is considered closed, and can reopen with a reason.

**Known limitations (honest list):**
- No push notifications or SMS — the student portal polls while a complaint is open, and the warden digest is in-app/copyable.
- Rate limiting and the digest AI-polish cache are in-memory per backend process (fine for one Render instance; needs Redis for horizontal scale).
- Single-hostel deployment: one tenant, blocks A–F assumption in UI hints only.
- AI covers the 4 maintenance trades; other problem types fall through to manual warden categorization.
- The AI's duplicate detector only sees the 5 most recent open complaints in the same block.

**2-minute demo script:** submit a photo complaint as the demo student → watch "My complaints" tick over → approve the AI suggestion as the warden (show reason + confidence + the "safety risk" escalation on an exposed-wiring photo) → complete the job as the worker → the student confirms "Yes, fixed" → warden Reports page shows repeat-problem alerts, hotspots, and the copyable daily digest.

**If something breaks live:** if Gemini is down or returns malformed output, complaints land safely in `WARDEN_REVIEW` with an "AI unavailable" note, the warden can hit **Re-run AI**, or simply assign manually — the product never blocks on the model.

---

## Privacy & Security Notes

- Use fake/demo data only
- All API keys stay server-side (backend `.env` / Render env vars)
- AI input/output is validated; the warden stays in the decision loop
- Strict file validation on every photo upload

## License

MIT — see [`LICENSE`](LICENSE).
