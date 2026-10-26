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
| `room` | text | yes |
| `photo` | JPEG file | no |

The response can be `{ "reference": "..." }`, `{ "id": "..." }`, or a successful response without a reference. If no reference is returned, the success screen shows `Pending`.

Set `VITE_API_BASE_URL` only when the API is deployed on a different origin. The key is public and publishable; never put a service-role key in frontend variables.

Signup is a single step: choose a role, enter a name, email, and password, and the account opens directly into the dashboard. The backend creates a confirmed Supabase Auth account and the matching shared `users` profile in the same request; Worker signup also creates its `workers` profile. The backend assigns trusted `app_metadata`; Student complaints use the authenticated Supabase access token and role-specific API routes enforce linked database roles.

The app creates confirmed users through the backend Admin API, so signup does not send or wait for an email. Keep the service-role key only in the backend environment; the browser uses the publishable key for sign-in.

## Production deployment

Build the frontend with `npm run build` and publish `dist/`. Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, and `VITE_API_BASE_URL` in the frontend host. The API base URL should be the deployed FastAPI origin when the frontend and API use separate hosts. Configure the static host to serve `index.html` for direct browser requests to `/student/*`, `/warden/*`, and `/worker/*` so role routes work after refresh. Set the backend `CORS_ORIGINS` to the exact deployed frontend origin.

## Checks

```bash
npm run lint
npm run build
npm run preview
```

Photos are validated in the browser, resized to a maximum edge of 1600 px, re-encoded as JPEG, and stripped of metadata before upload. Server-side validation is still required.
