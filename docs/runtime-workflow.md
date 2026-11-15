# Runtime workflow and review

Implemented development runtime: private context pinning; restartable local speech
and sampled visual indexing; text-only subscription Codex decisions through a local
Unix socket; durable decisions/observations; source-linked scripts; script approval;
OTIO A-roll/dialogue and one B-roll track; preview rendering with embedded soft
subtitles; export validation; sampled local visual review; XML/OTIO/SRT/media/MP4
handoff; revision-bound feedback and exact-candidate approval events.

This is a restricted implementation of the broader agent-contract design. Runtime
uses the strict `DECISION_SCHEMA` in `edie/agent.py`, not the entire proposed v1
message union. The coordinator supplies snapshot hashes and invocation identities;
models do not choose them. JSON arguments receive tool-specific semantic validation.
Unsupported effects, arbitrary track layouts and independent audio edits fail.

## Private configuration

`EDIE_CONFIG_DIR/context` contains the versioned strategy, SOUL.md and MEMORY.md.
A separate private routes JSON configures `speech` and `vision`: base_url, model,
accepted_models, billing (`local` or `subscription`), allowed_payloads, timeout,
max_tokens and optional credential_env. Actual credentials are runtime environment
variables, never JSON payloads. Paid routes and automatic fallback are rejected.
HTTP redirects are rejected to prevent payload leakage. TLS verification stays on.

Run `python -m edie.analysis --state STATE --media MEDIA --routes ROUTES
--manifest MANIFEST` for indexing. The broker manifest carries stable source ID,
version, local relative path and SHA-256. Speech uses 30-second mono 16 kHz chunks;
original service responses are retained. Invalid model timestamps are retained as
issues and excluded from timed subtitle candidates. Eight timestamped overview
frames provide a coarse first pass; `inspect_range` enables closer local inspection.
Sparse frame coverage must never be described as full motion/audio understanding.

## Decisions and execution

An operator-owned text broker runs `python -m edie.codex --socket SOCKET --model
MODEL`. It invokes the supported subscription CLI with ambient config/rules,
shell, apps, images and subagents disabled. Only approved text context is supplied.
The broker owns login/renewal; it does not copy credentials into workers. Its Unix
socket is mode 0600. A dedicated deployment login/account remains recommended;
the development trial uses the operator's existing subscription session. There is
no fallback to an API key. Authentication/transport uncertainty parks work.

The coordinator runs `python -m edie.daemon --state STATE --config CONFIG --media
MEDIA --socket SOCKET --routes ROUTES`. The CLI `python -m edie.agent` with the same
flags and `--job ID` runs a bounded batch. Model observations, decisions and usage
are stored privately. Plans are editable between turns; this is not a fixed stage
pipeline. The agent can inspect more evidence, propose a script, build a timeline,
render, evaluate, revise and request review. It cannot issue approval events.

The existing queue worker renders tasks in isolated process groups. The daemon
wakes after task completion without spending model calls on status polling. A
per-job file lock serializes decision writers; expected state versions fence stale
outputs after human feedback. Immutable abandoned candidates remain recoverable.
Invocations persist before execution. Uncertain completion is parked for explicit
operator reconciliation; no blind provider or export replay occurs. An operator
`recover` event records acknowledgement of unknown usage and abandons the uncertain
invocation before replanning. It does not claim the original call was free.

## Human events and dashboard

`/dashboard` serves a static shell without private data. A token entered there is
held in tab memory, never local storage or a URL. All data/API requests need bearer
authentication. The dashboard displays jobs, scripts, plans, previews, checks,
usage, approvals and delivery metadata, and accepts timestamped feedback.

- GET `/jobs/ID/workflow` includes candidate hashes and current state version.
- GET `/jobs/ID/events` returns durable human-event records.
- POST `/jobs/ID/run` with expected_state_version requests a coordinator turn.
- POST `/jobs/ID/events` accepts event_id, expected_state_version, actor, type and
  payload. Supported types: approve, feedback, revoke, pause, resume, cancel,
  human_return, recover and receipt. Exact event replay returns the original result;
  reused IDs with different payloads and stale updates fail.

`approve` payload is `{scope: script|main|final, candidate: exact_hash}`. Prerequisite
approvals are checked. Final approval does not publish: a matching broker receipt
is required to finish. Actor provenance is asserted by the trusted broker/operator,
not independently authenticated human identity. The management token must not be
provided to model workers.

`feedback` includes revision, timestamp, text and optionally accepted_for_learning
when explicitly accepted by a human. Old feedback remains attached to its original
revision. Human master import verifies hash/decode, copies into immutable state,
and requires a human_return event followed by main approval. Accepted masters are
preserved as authoritative; edit requests needing missing layers are blocked.

## Export and limitations

Preview and export use the same OTIO revision. Video uses fitted 1280×720, 720×1280 or 720×720 canvases at
30 fps, fitted with padding rather than automatic cropping. Boundaries quantize
to nearest 30 fps frame. Original source metadata/identity remains in the manifest.
This is a review format; source-native/VFR finishing fidelity needs further work.
B-roll replaces picture while retaining A-roll audio. Audio-only sources, effects,
custom graphics, animated titles, speed changes and arbitrary mixing are not yet
supported. Subtitles are source-derived and embedded as a selectable MP4 track,
with SRT sidecars; correction/translation and typography need human review.

Handoff independently copies source media, preserving originals even if an editor
modifies package files. FCP7 library roundtrip checks compare tracks by kind because
the adapter reorders audio/video tracks. Passing these checks does not establish
compatibility with a particular finishing application. Actual editor/version
roundtrip, human editorial acceptance and final delivery remain acceptance gates.

Storage admission checks state size and free-space floor before expensive work;
limits use EDIE_MAX_STATE_BYTES and EDIE_MIN_FREE_BYTES. No automatic deletion.
This conservative guard is not a concurrent disk-reservation ledger. Decision turns
are bounded; per-call usage and known incremental cost are recorded, subscription
allocation cost remains unknown. There is no metered spending in this runtime.

## Container lifecycle

Set EDIE_ROUTES_FILE, EDIE_MANIFEST_FILE, EDIE_CODEX_SOCKET and EDIE_MODEL_SOCKET
to private absolute paths. The client routes file names `/run/models.sock`; the
host-side model broker separately owns endpoint configuration. Start it with
`python -m edie.model_broker --socket SOCKET --routes HOST_ROUTES`. It permits only
the configured local vision and transcription endpoints and model IDs. It cannot
serve arbitrary URLs or filesystem paths. Both socket owners must match the
configured container UID/GID. Socket restart may require recreating containers
because a bind mount refers to the old inode.

`docker compose --profile index run --rm analysis` indexes the broker manifest.
`docker compose --profile agent up -d api worker coordinator` starts the workflow.
The analysis, coordinator and renderer have `network_mode: none`; local inference
and subscription text decisions use only the mounted restricted sockets. The API
uses its existing internal network and loopback port. Stop with
`docker compose --profile agent stop api worker coordinator`.
