# Editorial review workspace

The browser is an editorial control room. Edie owns rendering and detailed editing;
humans inspect evidence, select a story, adjust structure, give direction and approve.
The interface has one job list, a shared-library/output selector and five progressive views:

- Footage: source names, durations, searchable original transcripts, sparse visual
  observations, coverage warnings and lightweight source playback. Source timestamps
  seek the player. Observations are labelled sampled, not exhaustive.
- Segments: classified/ranked source ranges with visual boundary review and shared selection.
- Stories: retained script proposals, current selection, source-linked story beats,
  move-earlier/later structural changes and sequential source playback. This sequence
  preview is a browser assembly, not a rendered cut: no effects, graphics or subtitles.
  Script selection organizes the view without renaming or moving original files.
- Cuts: actual rendered MP4, validation findings and timestamped feedback bound to
  its revision. Main/final approval remain distinct from script approval.
- Activity: actual task states, workflow plan, human events, usage and failures. The
  direction box submits a durable instruction bound to the observed state version.

Deployment can configure `EDIE_REVIEW_WORKSPACES` as JSON entries with `label` and
same-origin `prefix`. One dashboard aggregates jobs from these API namespaces. These
are configured private API namespaces, not a new project model.
Each backend retains its own state, context and authorisation. Reverse proxies must
strip each prefix. No cross-origin tokens or public media URLs are introduced.

Implemented API additions (all bearer-authenticated):

- GET `/workspaces`: configured dashboard namespaces; defaults to this deployment.
- GET `/jobs/ID/footage`: job-scoped current-version indexes, transcript, visual
  descriptions and lightweight proxy task status. Uses the agent's same source scope.
- GET `/jobs/ID/tasks`: durable tasks for progress inspection.
- POST `/jobs/ID/sources/SOURCE_ID/proxy` with `{}`: deduplicated low-resolution
  proxy task keyed by source hash. Offline `python -m edie.editorial --state ...
  --media ...` workers process it with existing task leases/cancel/recovery.
- GET `/tasks/ID/artifact`: also accepts completed source proxies, supports a single
  byte range and rejects invalid/unsatisfiable ranges. The UI uses authenticated
  blob downloads; long proxies must finish downloading before first playback.
- Human events `select_script` (candidate hash) and `arrange_script` (candidate hash,
  complete clip-index permutation) retain proposal history and invalidate approvals.
  They are permitted before a timeline revision exists. Dependent overlays/graphics
  require agent reconciliation rather than naive reorder. These actions do not render.

Playback proxies are at most 640 pixels per side, 24 fps, H.264/AAC. They use
rotation-aware decoding and HDR-to-SDR conversion, preserve originals and verify
source hash/duration. They are review aids, not finishing media or native frame maps.

Polling updates status without replacing active text drafts or the player. Draft
instructions are isolated by job; stale writes fail. Approval always references the
current candidate hash, never an unsubmitted reorder or older proposal.

Not provided: a full NLE, frame-accurate browser edits, waveform editing, visual
caption styling, automatic editorial acceptance, or source-store reorganisation.

Validation: synthetic real-browser acceptance covers source playback, transcript
search, retained proposal selection, reorder, approval invalidation, isolated job
instruction drafts and a 390px viewport without horizontal overflow or JavaScript
errors. Run `tests/browser_editorial.py` with Playwright/Chromium, FFmpeg and Edie
installed; provide writable `/output` for screenshots. Unit/integration coverage
also verifies job source scope, proxy-task deduplication, actual FFmpeg proxy output,
authenticated media ranges and protected human revisions. This does not constitute
finishing-application acceptance or approval of real editorial outputs.

Run the `proxy-worker` Compose service alongside API/worker to prepare browser
playback copies. Proxy queues use no model routes. They are recoverable through the
same task controls as renders. The UI currently polls every ten seconds and shows
state transitions, not a fabricated completion percentage or token stream.


## Intake, segment review and story gate

Files have Edie-first Keep / Exclude / Needs-review decisions, with human overrides. Editorial roles, Blooper,
intrinsic usefulness and brief-fit scores belong to source-linked segments. Human
Available / Selected / Rejected decisions are separate from roles. Whole-file role
classification, its editing endpoint and runtime legacy-label translations have been
removed; development records are migrated explicitly by the operator.

The Segments panel supports source-range playback, context handles, role toggles,
selection, ranking/filtering, save-next, split and merge. Its visual range editor
provides draggable start/end handles, precise fields, neighbour view, zoom, seek and
draft preview. Filmstrip frames are decoded in-browser from the local proxy, with no
model request. Saving both bounds is atomic and revision-checked. Adjacent ranges
adjust; first/last trims retain reviewable remainder segments. Unsaved drafts block
footage confirmation. Source playback is for review, not frame-accurate finishing.

Flagged files require human intake; confident automatic decisions are accepted without
a per-file click. Every kept source needs segments before confirming the
exact selection. Excluded sources and rejected segments cannot enter scripts. New
scripts reference segment IDs, bounds and trims; changed segment boundaries require
fresh review. Confirmation allows story proposals, not script or render approval.
The user approves a chosen script before Edie builds a cut. See the complete storage,
API and reasoning design in [editorial segments](editorial-segments.md).

Indexing/segmentation counts appear independently of the editorial stage. Running
analysis need not change a job's story stage. The dashboard polls counts without
replacing unsaved forms or interrupting playback; refresh loads newly prepared rows.

Current state projection, independent story outputs, file properties and responsive layout are documented in [editorial progress and outputs](editorial-progress-and-outputs.md).

See [ranked automatic intake](ranked-intake.md) for the implemented decision policy,
review threshold, low-to-high review mode and in-player source playback.
