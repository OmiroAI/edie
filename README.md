# Edie

A self-hostable video editor assistant under construction. This initial slice is
an editing core with a development API and queue worker, **not the complete product**. No fleet configuration,
credentials, deployment context or footage belongs in this repository.

Implemented: persistent video jobs and briefs, immutable timeline revisions,
revision-bound feedback/approval primitives, source hash checks, mounted-path
containment, and FFmpeg clip assembly with duration and decode validation.
Rendering currently normalises to 720p/30fps and requires audio on every clip.
It does not implement B-roll layers, transitions, graphics or subtitles yet.

## Local use

Requires Python 3.11+ and FFmpeg/ffprobe. Install with `pip install -e .`.
Run `python -m unittest discover -s tests -v`.

```
edie job '{"goal":"Explain","audience":"Beginners","format":"16:9","duration":30,"language":"en"}'
edie revision JOB_ID '[{"path":"clip.mp4","sha256":"ACTUAL_SHA256","in":0,"out":5}]'
edie render REVISION_ID --media /authorised/local/footage
```

State defaults to `./state`; use `--state` before the subcommand to override.
Originals are read only. A revision renders to its own private output directory.
No remote storage, model requests, publishing or paid fallback occurs.

## Container lifecycle

Set EDIE_MEDIA and EDIE_STATE to explicit absolute host directories. The state
directory must be writable by UID 10001. Keep runtime configuration private.

```
docker compose build
docker compose run --rm docker compose run --rm edie render REVISION_ID --media /media
```

The CLI and worker containers have no network, Docker socket or host credentials.
The API exposes only a loopback port through an internal Docker network. Stop a running
CLI container to interrupt it; partial outputs remain unaccepted. Rerunning a
render currently regenerates it, so this is not durable task recovery yet.
To run the API and queue worker, copy `.env.example` to a private `.env`,
configure the paths and token, then run `docker compose up -d api worker`.
Stop them with `docker compose stop api worker`. The token is passed only to
the API, not the worker. Never expose the development API directly to the Internet.

Back up the state directory with all writers stopped. Upgrade by backing up,
checking out reviewed source and rebuilding. Do not delete source copies while
jobs are unfinished. API and worker services are available in Compose; no production deployment has been performed.

One deployment owns one private editorial context; video jobs are its stories.
There is no project-creation step.

See [agent contracts for review](docs/agent-contracts.md),
[finishing-editor adapters](docs/editor-adapters.md), [OTIO timeline design](docs/timeline.md), [strategy and evaluation](docs/strategy-evaluation.md),
[handoff and feedback](docs/handoff-feedback.md), [agentic loop](docs/agent-loop.md), [storage policy](docs/storage.md), [model access](docs/model-access.md),
[system design](docs/system.md), [API contract](docs/api.md),
[footage catalogue and preprocessing](docs/footage-index.md),
[implementation gates](docs/implementation-gates.md), the proposed
[visual analysis and review pipeline](docs/visual-analysis.md), and
[contributor instructions](AGENTS.md).

## Management API (development)

Supply a private `EDIE_API_TOKEN` of at least 32 characters at runtime, then run
`python -m edie.api`. It binds to loopback port 8080 by default. `EDIE_STATE`,
`EDIE_BIND` and `EDIE_PORT` configure it. Use a TLS reverse proxy for remote access;
this development HTTP server is not a production-facing gateway.

Every route requires `Authorization: Bearer TOKEN`, including `/health`.
GET `/jobs`, `/revisions` lists records; append `/ID` to retrieve
one record. POST to these routes creates records using the same field names as
the CLI. POST `/feedback` accepts job, revision, text and timestamp. POST
`/approvals` accepts job and revision.

POST `/tasks` accepts job and revision, requires an `Idempotency-Key` header,
and durably queues a render request. GET `/tasks/ID` reads status. POST
`/tasks/ID/pause`, `/resume`, `/cancel` or `/recover` with an empty JSON object
performs a guarded transition. Running pause/cancel requests stop the render process
before acknowledgement. Resume starts a new attempt; expired leases require
explicit recovery. Run `python -m edie.worker --state state --media /authorised/media`
to process queued renders, or add `--once` for a single task. Completed previews
are available at the authenticated `/tasks/ID/artifact` route. See the API and
system documents for recovery limits and remaining production gaps.
