# API overview

Interactive OpenAPI documentation is exposed at `/docs` by FastAPI.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service, model, and storage status without exposing secrets |
| `GET` | `/api/session` | Establish the anonymous browser session and report access-gate state |
| `GET` | `/api/samples` | Public-domain sample catalog |
| `GET` | `/api/media/{key}` | Read an image only when it belongs to the current browser session |
| `POST` | `/api/samples/{id}/import` | Download a sample into a local project |
| `POST` | `/api/projects` | Upload an artwork plus stage, style, and original intent |
| `GET` | `/api/projects` | Recent project history |
| `POST` | `/api/projects/{id}/intent/restate` | Generate the confirmation-ready intent reading |
| `POST` | `/api/projects/{id}/analyze` | Confirm intent and run the four-dimensional critique |
| `GET` | `/api/analyses/{id}` | Load a saved analysis |
| `PATCH` | `/api/analyses/{id}/suggestions/{id}` | Persist a corrected normalized rectangle |
| `POST` | `/api/analyses/{id}/feedback` | Store useful, not useful, or intentional feedback |
| `POST` | `/api/projects/{id}/revisions` | Upload a revision and generate the comparison report |

All AI outputs are validated by Pydantic before persistence. Uploads accept JPG, PNG, or WebP, default to 15 MB maximum, and reject images above 30 megapixels.

Every browser receives an HttpOnly anonymous session cookie. Project, analysis, feedback, revision, and media routes enforce that ownership boundary. When `DEMO_ACCESS_CODE` is configured, protected routes first require `X-ArtMentor-Access-Code`; a successful check creates a one-day HttpOnly access cookie so normal image elements remain authorized. AI and upload endpoints also apply per-IP in-memory limits.

`GET /api/health` returns the selected provider, whether that provider is configured, and its model ID. It never returns a key or the configured Base URL.
