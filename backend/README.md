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

1. Create the project, then run migrations against its PostgreSQL:

   ```powershell
   # psql (Supabase Dashboard > SQL editor): CREATE DATABASE lookup not needed (postgres exists);
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```
2. Create the **private** bucket in Dashboard > Storage > New bucket:
   name `complaint-photos`, Public = **off**.
3. Fill `.env` with `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   (both from Dashboard > Settings > API), keeping `SUPABASE_STORAGE_BUCKET=complaint-photos`.
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

Then open <http://127.0.0.1:8000/docs> (Swagger) or <http://127.0.0.1:8000/redoc>.
`GET /health` now also reports database connectivity
(`{"status":"ok","database":"connected"}`).

Until `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are filled in, photo storage
falls back to the local `uploads/` directory so development still works.

## Demo authentication

For the MVP the API identifies users with the `X-User-Id` header (see
`seed.py` output for demo ids: 1–2 students, 3 warden, 4–7 workers).
`app/core/security.py` centralises the lookup, so swapping in JWT later only
means replacing `get_current_user`.

## API overview

| Method | Path | Who | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | public | health + database connectivity |
| GET | `/` | public | welcome message |
| POST | `/complaints` | student | submit complaint (multipart: `description`, `block`, `room`, optional `photo`) |
| GET | `/complaints` | warden | full complaint queue |
| GET | `/complaints/{id}` | owner / warden / assigned worker | role-scoped detail incl. status history |
| GET | `/complaints/{id}/photo` | owner / warden / assigned worker | private photo bytes (no storage keys leaked) |
| GET | `/complaints/{id}/photo/url` | owner / warden / assigned worker | temporary signed URL (Supabase Storage only) |
| PATCH | `/complaints/{id}/review` | warden | final category/severity/worker + warden note → creates task |
| GET | `/tasks/my` | worker | only their assigned tasks |
| PATCH | `/tasks/{id}/status` | worker | ASSIGNED → IN_PROGRESS → COMPLETED (+ note) |
| GET | `/alerts` | warden | active repeat-problem alerts (deterministic rule) |
| GET | `/digest` | warden | daily summary (no AI) |

Photos are uploaded once at complaint-creation time, stored privately under
`complaints/{complaint_id}/{uuid}.{ext}`, and the DB keeps only that key.

## Environment

See `.env.example`. Key settings: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `GEMINI_API_KEY`,
`GEMINI_MODEL`, `CORS_ORIGINS`, `TASK_OVERDUE_HOURS`, `MAX_IMAGE_SIZE_MB`.

Without `GEMINI_API_KEY` (or with an unusable model name) the app still works:
complaints skip AI analysis and land straight in `WARDEN_REVIEW` for manual
categorisation — by design.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

53 tests cover health, complaint validation, student ownership, warden access,
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
- The React student screen currently sends a combined `room` value; it will
  need to send the separate `block` + `room` fields expected here.
- `gemma-4-31b-it` returned HTTP 500 (unavailable) for our key during testing;
  `GEMINI_MODEL` is env-configurable and any callable model name works,
  e.g. `gemini-2.5-flash`.
- No scheduler: overdue is computed on the fly from `TASK_OVERDUE_HOURS`.
