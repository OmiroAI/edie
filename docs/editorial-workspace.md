# Editorial review workspace

The browser is an editorial control room. Edie owns rendering and detailed editing;
humans inspect evidence, select a story, adjust structure, give direction and approve.
The interface has one job list and four views:

- Footage: source names, durations, searchable original transcripts, sparse visual
  observations, coverage warnings and lightweight source playback. Source timestamps
  seek the player. Observations are labelled sampled, not exhaustive.
- Story: retained script proposals, current selection, source-linked story beats,
  move-earlier/later structural changes and sequential source playback. This sequence
  preview is a browser assembly, not a rendered cut: no effects, graphics or subtitles.
  Script selection organizes the view without renaming or moving original files.
- Review: actual rendered MP4, validation findings and timestamped feedback bound to
  its revision. Main/final approval remain distinct from script approval.
- Activity: actual task states, workflow plan, human events, usage and failures. The
  direction box submits a durable instruction bound to the observed state version.

Deployment can configure `EDIE_REVIEW_WORKSPACES` as JSON entries with `label` and
same-origin `prefix`. One dashboard aggregates jobs from these API namespaces. This
is a compatibility bridge for existing separate state roots, not a new project model.
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


## Editorial classification

Classification is a job-scoped second pass after reusable transcript/visual indexing.
It uses explicitly authorised text-only subscription Codex; no media leaves the local
inference setup. The queue index worker accepts `--classification-socket` and Compose
wires it to the broker. Standalone raw `edie.analysis` indexing has no story/job context;
run `python -m edie.classification --state ... --config ... --job ... --socket ...`
after it. This command also classifies previously indexed jobs without retranscription.

Overlapping roles: A-roll, B-roll, hook, demonstration, reaction, establishing and
needs-review. Reject candidate (`throw_away`) is an editorial flag, never deletion.
Sparse observations, absent speech and poor ASR do not establish unusable footage.
Exact byte duplicates are hash-checked; near-duplicates are not automatically proven.
Each model suggestion contains a reason, confidence, job-usefulness score and up to
three source-timed moments. Up to five non-rejected sources receive automatic star
ranks across the whole job. Scores rank suggestions, not objective footage quality.
Long transcripts are sampled across their duration; whole-video certainty is not claimed.

Suggestions are cached by source evidence, source hash, job brief, private context
and classifier profile. Changed evidence is reclassified; renames preserve human labels.
Human overrides are stored separately and win over reruns. Resetting to agent labels
is explicit, and both suggestions and edits have an append-only audit history.
Classification keys include job/source ID/version/hash; changed media cannot inherit
an old approval-like human decision. Stars can be added/removed by humans; the five-star
limit applies to the automatic shortlist, not to an operator's personal selects.
The agent receives effective labels in its planning context. Labels do not approve or
rewrite a script or automatically cut anything from an accepted edit.

GET job footage includes suggestion, override, effective classification and revision.
POST `/jobs/ID/sources/SOURCE/classification` requires source_version, source_sha256,
expected_revision, labels and a reason; `reset:true` restores the suggestion. Stale
versions and conflicting reject/star combinations fail. The browser supports label
filters and sorting by stars/usefulness, filename, duration or current script order.


### Mandatory footage review before story development

The workflow is indexing/classification → human footage confirmation → 2–3 story
options → script selection/refinement/approval → rough cut → cut review/delivery.
All indexed sources must have an effective classification (human labels can fill in
missing suggestions), and at least one must be included. The `confirm_footage` event
binds the confirmation to a digest of current source versions/hashes and visible
classification decisions. Changed classifications or sources invalidate confirmation.
Workers and approval endpoints enforce this gate. Existing unapproved drafts remain
stored but do not bypass it. No actual human confirmation is synthesized during migration.

Confirmed reject candidates are excluded from agent source summaries, evidence reads
and clip resolution. To reinclude a reject, the human must change its labels and
reconfirm. `propose_stories` returns two or three distinct source-linked proposals;
these still require script selection/approval. A confirmation never approves a render.
Human-authored/accepted timeline revisions remain protected; classification review
does not automatically replace an already accepted edit.

GET workflow includes `footage_review` counts, excluded IDs, candidate digest, readiness
and confirmation status. POST job events accepts `type:confirm_footage` with
`payload:{candidate:...}` plus the existing event ID, state version and actor fields.
Selecting this event wakes planning only after the exact reviewed selection matches.

Manual classification is opened by the prominent **Edit labels** button beside
**Play source** above the selected video's player. Saving labels preserves the
agent suggestion separately and requires reconfirming the footage selection.

Classification mode freezes the currently filtered/sorted clip queue, presents horizontal
role/selection/decision toggles beside playback, and advances only after a successful
Save & next. Previous/Skip do not save; unsaved label drafts are retained per job/source
in tab memory. Unsaved drafts block footage confirmation. Finishing the queue exits
review mode without confirming footage or requesting scripts automatically.

Human instructions/feedback and explicit recovery start a new agent intent scope.
Read/tool reservations are scoped to that intent and the confirmed selection so an
old successful evidence read does not falsely block a new requested story. Render
task idempotency remains tied to the revision; this does not authorize duplicate exports.
