# HostelDesk web app

The shared Student, Warden, and Worker web app for HostelDesk. All three portals use the same Supabase Auth project. The student complaint dashboard is `/student/dashboard`; role sign-in and registration pages are under `/student`, `/warden`, and `/worker`.

## Run locally

```bash
npm install
npm run dev
```

Open the URL printed by Vite. The dev proxy sends API requests to FastAPI at `127.0.0.1:8000`.

## Connect the API

Create `.env.local` from `.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

The app sends a `multipart/form-data` request to `POST /complaints`:

| Field | Type | Required |
| --- | --- | --- |
| `description` | text | yes |
| `block` | text | yes |
| `room` | text | yes |
| `photo` | JPEG file | no |

The response can be `{ "reference": "..." }`, `{ "id": "..." }`, or a successful response without a reference. If no reference is returned, the success screen shows `Pending`.

In local development, the blank `VITE_API_BASE_URL` uses Vite's API proxy. Production defaults to `https://hosteldesk-qgx8.onrender.com`; set `VITE_API_BASE_URL` only when deploying against a different FastAPI origin. The Supabase key is public and publishable; never put a service-role key in frontend variables.

Signup is a single step: choose a role, enter a name, email, and password, and the account opens directly into the dashboard. The backend creates a confirmed Supabase Auth account and the matching shared `users` profile in the same request; Worker signup also creates its `workers` profile. The backend assigns trusted `app_metadata`; Student complaints use the authenticated Supabase access token and role-specific API routes enforce linked database roles.

The app creates confirmed users through the backend Admin API, so signup does not send or wait for an email. Keep the service-role key only in the backend environment; the browser uses the publishable key for sign-in.

## Production deployment

The production frontend is deployed at **https://hosteldesk.aurio.workers.dev** (Cloudflare Workers static assets).

Build and deploy:

```bash
npm run build
npx wrangler deploy
```

`wrangler.jsonc` configures the Worker (`hosteldesk`) with `dist/` as the assets directory and single-page-application fallback, so `/student/*`, `/warden/*`, and `/worker/*` routes render the app after a refresh instead of 404ing. One caveat verified live: a hard refresh of a deep-linked warden sub-page (e.g. `/warden/reports`) re-routes to the warden overview once the session is restored — navigate via the sidebar tabs after refreshing.

Set these Supabase build-time variables in `frontend/.env` before building. `VITE_API_BASE_URL` is optional because the production build defaults to the Render API origin:

```env
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable key>
# Optional override for a different FastAPI deployment:
# VITE_API_BASE_URL=https://api.example.com
```

Supabase values are compiled into the bundle at build time — if either is missing, `createClient` returns `null` and the portal shows "Authentication is not configured." API calls use the FastAPI origin, not the Cloudflare SPA host, to avoid receiving `index.html` where JSON is expected. The publishable key is public by design; never put a service-role key in frontend variables. The backend `CORS_ORIGINS` on Render must include the exact deployed frontend origin (`https://hosteldesk.aurio.workers.dev`).

## Checks

```bash
npm run lint
npm run build
npm run preview
```

Photos are validated in the browser, resized to a maximum edge of 1600 px, re-encoded as JPEG, and stripped of metadata before upload. Server-side validation is still required.
