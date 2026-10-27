# HostelDesk Backend

FastAPI backend for the AI-assisted hostel complaint and task desk.

**Central rule: AI suggests; the Warden decides.** Gemma/Gemini only classifies
a complaint (category / severity / suggested worker type); it never assigns a
worker. The warden's review creates the task.

## Stack

Python 3.11 · FastAPI · SQLAlchemy 2.x · Pydantic v2 · pydantic-settings ·
Alembic · Supabase PostgreSQL · Supabase Storage (photos) · python-multipart ·
httpx (Gemini REST) · pytest

```text
React → FastAPI → SQLAlchemy → Supabase PostgreSQL
FastAPI → Supabase Storage (private bucket)
FastAPI → Gemma/Gemini (server-side only)
```

## Quick start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env        # then edit DATABASE_URL / SUPABASE_* / GEMINI_API_KEY
```

### Supabase setup (once per project)

1. Create the project, then run migrations against its PostgreSQL with an
   owner-level connection. Keep the runtime API connection on the dedicated
   `hosteldesk_app` role:

   ```powershell
   $env:MIGRATION_DATABASE_URL = "postgresql+psycopg2://postgres:<database-password>@db.<project-ref>.supabase.co:5432/postgres"
   .\.venv\Scripts\python.exe -m alembic upgrade head
   Remove-Item Env:MIGRATION_DATABASE_URL
   ```

   Get the direct connection string from Supabase Project Settings → Database.
2. Create the **private** bucket in Dashboard > Storage > New bucket:
   name `complaint-photos`, Public = **off**.
3. Fill `.env` with the runtime `DATABASE_URL`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY` (from Dashboard > Settings > API); keep
   `SUPABASE_STORAGE_BUCKET=complaint-photos`. The service-role key stays on
   the backend and is used for server-side account creation and private storage.
4. Verify the wiring without starting the app:

   ```powershell
   .\.venv\Scripts\python.exe scripts\verify_supabase.py
   ```

   The script checks the DB, uploads + reads back a test object, prints a
   short-lived signed URL, then cleans up.
5. Seed demo data and run:

   ```powershell
   .\.venv\Scripts\python.exe seed.py            # demo data; add --reset to wipe first
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
   ```

   Apply the Warden Auth/profile/RLS migration before starting the Warden portal:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

Then open <http://127.0.0.1:8000/docs> (Swagger) or <http://127.0.0.1:8000/redoc>.
`GET /health` now also reports database connectivity
(`{"status":"ok","database":"connected"}`).

Until `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are filled in, photo storage
falls back to the local `uploads/` directory so development still works.

## Authentication

Students, Wardens, and Workers use the same Supabase Auth project. The backend
verifies each access token and checks the linked database role. Profiles link
to their Supabase account through `users.auth_user_id`.

### Role signup

Signup creates a confirmed Supabase Auth user and its HostelDesk role profile
in one server request. It does not send an email or wait for a confirmation
step. Student signup assigns only the Student role. Warden and Worker signup
sets trusted `app_metadata` and links the account through `users.auth_user_id`;
Worker signup also creates a row in the existing `workers` table. The service-role
key is never embedded in frontend source.

Staff signup is protected by an invite code checked by the backend before an
account is created. Configure `WARDEN_SIGNUP_CODE` and `WORKER_SIGNUP_CODE` for
separate role codes. `STAFF_INVITE_CODE` is an optional shared fallback; a
role-specific value takes precedence. If neither code applies, that role's
signup returns `403 Staff signup is disabled.` The student signup endpoint is
not gated by these settings.

The backend check is constant-time and never logs the supplied code:

```python
role_code = settings.warden_signup_code if role is UserRole.WARDEN else settings.worker_signup_code
expected = role_code or settings.staff_invite_code
if not expected:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff signup is disabled.")
if not invite_code or not hmac.compare_digest(invite_code.strip().encode(), expected.encode()):
    raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid staff invite code is required.")
```

For production, set the invite-code values only in the backend service's secret
environment (Render → `HostelDesk` → Environment), then deploy the service.
Share each invite code only with the staff members who need to register; never
put a real code in source control, screenshots, or public docs.

## API overview

| Method | Path | Who | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | public | health + database connectivity |
| GET | `/health/ai` | public | AI service readiness (model + API key status) |
| GET | `/` | public | welcome message |
| POST | `/complaints` | student | submit complaint (multipart: `description`, `block`, `room`, optional `photo`) |
| GET | `/complaints` | warden | complaint queue; optional `status`, `category`, `severity`, `search`, and `sort` filters |
| GET | `/complaints/mine` | student | only the signed-in student's complaints |
| GET | `/auth/warden/me` | authenticated Warden | linked Warden profile |
| GET | `/auth/me` | authenticated role | linked profile and role |
| POST | `/auth/student/signup` | public | create confirmed Student account and profile |
| POST | `/auth/warden/signup` | public | create confirmed Warden account and profile |
| POST | `/auth/worker/signup` | public | create confirmed Worker account and profile |
| GET | `/warden/dashboard` | warden | complaint totals, recent reports, and worker workload |
| GET | `/warden/workers` | warden | worker availability and active task counts |
| GET | `/warden/reports` | warden | status/category totals and daily digest |
| GET | `/complaints/{id}` | owner / warden / assigned worker | role-scoped detail incl. status history |
| GET | `/complaints/{id}/photo` | owner / warden / assigned worker | private photo bytes (no storage keys leaked) |
| GET | `/complaints/{id}/photo/url` | owner / warden / assigned worker | temporary signed URL (Supabase Storage only) |
| PATCH | `/complaints/{id}/review` | warden | final category/severity/worker + warden note → creates task |
| GET | `/tasks/my` | worker | only their assigned tasks |
| PATCH | `/tasks/{id}/status` | worker | ASSIGNED → IN_PROGRESS → COMPLETED (+ note) |
| GET | `/alerts` | warden | active repeat-problem alerts (deterministic rule) |
| GET | `/digest` | warden | deterministic daily counts with an optional AI-polished Activity / Queue / Patterns summary |

Photos are uploaded once at complaint-creation time, stored privately under
`complaints/{complaint_id}/{uuid}.{ext}`, and the DB keeps only that key.

## Environment

See `.env.example`. Key settings: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `GEMINI_API_KEY`,
`GEMINI_MODEL`, `CORS_ORIGINS`, `STAFF_INVITE_CODE`,
`WARDEN_SIGNUP_CODE`, `WORKER_SIGNUP_CODE`, `TASK_OVERDUE_HOURS`,
`MAX_IMAGE_SIZE_MB`.

Without `GEMINI_API_KEY` (or with an unusable model name) the app still works:
complaints skip AI analysis and land straight in `WARDEN_REVIEW` for manual
categorisation — by design. The digest also falls back to the same concise,
three-line rules-based summary when AI polish is unavailable.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

74 tests cover AI readiness, complaint validation including separate block/room
fields, student ownership, Warden auth and single-request signup, Warden
dashboard/workers/filters,
worker task ownership, the warden review gate, worker completion, the
repeat-problem rule, the digest, safe handling of invalid Gemini output,
storage (validation, safe filenames, fake Supabase client, signed URLs),
FK integrity, and Alembic upgrade/downgrade reproducibility.

## Notes / MVP limitations

- Supabase Storage uploads happen server-side with the service-role key; the
  React app receives photo bytes from `/photo` or a signed URL from
  `/photo/url` — the bucket stays private and the service key never leaves
  the backend.
- Complaint upload succeeds before the row commit; a DB failure after a
  successful Storage upload can leave an orphaned object (acceptable MVP).
- The React student form sends the separate `block` + `room` fields the API
  expects, matching the multipart contract of `POST /complaints`.
- `gemma-4-31b-it` returned HTTP 500 (unavailable) for our key during testing;
  `GEMINI_MODEL` is env-configurable and any callable model name works,
  e.g. `gemini-2.5-flash`.
- No scheduler: overdue is computed on the fly from `TASK_OVERDUE_HOURS`.
