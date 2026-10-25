# HostelDesk student portal

The student-facing complaint submission screen for HostelDesk. It is a Vite + React app with no runtime dependencies beyond React.

## Run locally

```bash
npm install
npm run dev
```

Open the URL printed by Vite. Without an API URL, development mode uses a local preview adapter: submission waits briefly and returns a clearly labelled preview reference, so the whole flow can be reviewed without a backend.

## Connect the API

Create a `.env` file in this folder (or set the variable in your shell):

```env
VITE_API_BASE_URL=http://localhost:8000
```

The app sends a `multipart/form-data` request to `POST /complaints`:

| Field | Type | Required |
| --- | --- | --- |
| `description` | text | yes |
| `room` | text | yes |
| `photo` | JPEG file | no |

The response can be `{ "reference": "..." }`, `{ "id": "..." }`, or a successful response without a reference. If no reference is returned, the success screen shows `Pending`.

When `VITE_API_BASE_URL` is empty in a production build, requests go to `/complaints` on the same origin.

## Checks

```bash
npm run lint
npm run build
npm run preview
```

Photos are validated in the browser, resized to a maximum edge of 1600 px, re-encoded as JPEG, and stripped of metadata before upload. Server-side validation is still required.
