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
| `POST` | `/api/projects/{id}/intent/restate` | Visually audit action/stage uncertainty and generate the confirmation-ready intent reading |
| `POST` | `/api/projects/{id}/analyze` | Confirm intent, stage, and optional action context, then run the stage-aware critique |
| `GET` | `/api/analyses/{id}` | Load a saved analysis |
| `PATCH` | `/api/analyses/{id}/suggestions/{id}` | Persist a corrected normalized rectangle |
| `POST` | `/api/analyses/{id}/feedback` | Store useful, not useful, or intentional feedback |
| `POST` | `/api/projects/{id}/revisions` | Upload a revision and generate the comparison report |
| `GET` | `/api/projects/{id}/pose-inspection` | Restore the latest artwork-only skeleton/check, or `null` |
| `POST` | `/api/projects/{id}/pose-inspection/estimate` | Estimate one editable artwork skeleton inside a user box |
| `PUT` | `/api/projects/{id}/pose-inspection/skeleton` | Persist artwork keypoint corrections and confirmation |
| `POST` | `/api/projects/{id}/pose-inspection/check` | Run conservative no-reference 2D consistency checks |
| `POST` | `/api/projects/{id}/pose-comparisons` | Upload a trusted pose reference and choose a style tolerance |
| `GET` | `/api/projects/{id}/pose-comparisons/latest` | Restore the latest editable pose-check snapshot, or `null` when none exists |
| `GET` | `/api/pose-comparisons/{id}` | Read one owned pose comparison |
| `POST` | `/api/pose-comparisons/{id}/estimate` | Estimate artwork/reference COCO-17 skeletons inside user boxes |
| `PUT` | `/api/pose-comparisons/{id}/skeletons` | Persist corrected keypoints and confirmation state |
| `POST` | `/api/pose-comparisons/{id}/compare` | Compare two confirmed skeletons with deterministic geometry |

All AI outputs are validated by Pydantic before persistence. Uploads accept JPG, PNG, or WebP, default to 15 MB maximum, and reject images above 30 megapixels.

Every browser receives an HttpOnly anonymous session cookie. Project, analysis, feedback, revision, and media routes enforce that ownership boundary. When `DEMO_ACCESS_CODE` is configured, protected routes first require `X-ArtMentor-Access-Code`; a successful check creates a one-day HttpOnly access cookie so normal image elements remain authorized. AI and upload endpoints also apply per-IP in-memory limits.

`GET /api/health` returns the selected provider, whether that provider is configured, its model ID, and the configured pose-provider mode. It never returns a key or the configured Base URL.

Pose coordinates are normalized to the complete source image. A skeleton contains
all 17 COCO points, model confidence, source (`model` or `user`), visibility, the
person bounding box, and confirmation state. Confidence expresses localization
uncertainty, not anatomical correctness. The compare route returns `409` until
both sides have been explicitly confirmed.

The artwork-only check follows the same confirmation rule. Its result is
deliberately narrower than reference comparison: it can flag only broad,
unusual 2D segment ratios, very large projected left/right differences, and
visible support-span alignment. It cannot declare absolute anatomical
correctness.
