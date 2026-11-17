# Management API

Status: development HTTP API, not a production-facing gateway. Configure
`EDIE_API_TOKEN` (at least 32 characters), `EDIE_STATE`, `EDIE_BIND` (default
127.0.0.1) and `EDIE_PORT` (8080). Supply private secrets through runtime
configuration. A TLS reverse proxy is required for remote access.

All routes, including health and artifact downloads, require
`Authorization: Bearer TOKEN`. JSON requests are limited to 1 MiB. Responses
use `Cache-Control: no-store`; request paths/bodies are not logged.

| Method/path | Contract |
| --- | --- |
| GET /health | Service liveness |
| GET /jobs, /revisions | List shared records |
| GET /jobs/ID, /revisions/ID | Read one record |
| POST /jobs | `brief` containing goal, audience, format, duration, language |
| POST /revisions | `job`, nonempty `clips` with local path, SHA-256, in/out seconds |
| POST /feedback | `job`, `revision`, `text`, `timestamp` in seconds |
| POST /approvals | `job`, `revision`; records intent, not a full release gate yet |
| POST /tasks | `job`, `revision`; requires Idempotency-Key header; queues render |
| GET /tasks/ID | State, payload, lease and result metadata |
| GET /tasks/ID/artifact | Completed preview as video/mp4; no range support yet |
| POST /tasks/ID/ACTION | Empty JSON object; action described below |

Creation returns 201 and an `id`. Reusing a task idempotency key for identical
input returns the same ID; different input is rejected. Invalid inputs/state
conflicts currently return 400, missing routes 404, missing/invalid credentials
401, and absent/oversized request bodies 413. Missing records currently return
400; more precise typed errors and schema validation are pending.

Task actions: `pause` accepts queued/running; `resume` accepts paused; `cancel`
accepts queued/paused/running/pause_requested; `recover` accepts interrupted/failed.
Running controls are acknowledged only after the worker stops its process group.
A worker must be polling for controls and expired-lease reconciliation to progress.
A completed task result contains revision, artifact path, bytes, SHA-256 and kind.
Clients should use the artifact route rather than treating the path as a host URL.

Run the API with `python -m edie.api` and a worker with
`python -m edie.worker --state /private/state --media /authorised/media`.
Add `--once` to process at most one task. Workers need no API token.

## Deployment scope

Each deployment owns one editorial context. There are no project routes or project
IDs; POST /jobs accepts only a brief, without a project selector. Jobs are individual
stories, while source metadata is reusable across jobs in this deployment.

With `EDIE_CONFIG_DIR` configured, job creation pins the active context's hash,
strategy ID and version in the job's `context` field. Private SOUL/MEMORY text is
not returned in job records. Missing or invalid context rejects creation.
Context installation and activation are operator CLI actions, not API routes.
See [configuration](configuration.md) for snapshot and rollback semantics.

Pre-change development databases containing project records are rejected at startup
rather than silently merging their contexts. Preserve the original state directory
and use a fresh state directory for this development version. No automatic data
migration or deletion occurs; a selective migration tool is still needed if those
historical jobs must be resumed. Old media and output files remain untouched.

See [multicam sessions and audio-led layers](multicam-and-layers.md) for camera alignment, review gates, API contracts and picture coverage.

See [synchronized editorial moments](editorial-segments.md#synchronized-editorial-moments) for grouped segment review, the moments API and duplicate-dialogue planning guards.
