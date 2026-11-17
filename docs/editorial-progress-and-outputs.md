# Editorial progress, job libraries and independent outputs

Implemented in the API and dashboard. One job owns a shared footage/segment library
and can produce multiple independent story outputs. This does not introduce projects;
deployment editorial context remains private configuration.

## Visible workflow

The interface shows Footage → Segments → Stories → Cuts, with Activity as a permanent
monitor rather than a completion gate. Each card carries a status and concrete counts.
Blue means work in progress, amber means human review, green means ready, grey means
pending/up to date, and red means intervention. Labels/icons accompany colours.

`GET /jobs/{id}/progress` is a read-only projection of current intake, indexes, segment
records, exact selection confirmation, workflow approvals and durable tasks. The same
object is returned as `workflow.progress`. Its `phase` is footage, segments, stories,
cuts or complete; `raw_stage` retains the agent's finer execution state. A stored
`review_script` stage cannot make newly unreviewed footage appear ready. Progress reads
never manufacture approvals or mutate execution state.

The response includes `mode`, `headline`, `working`, `needs_intervention`, an `action`
(label, detail, tab and optional output ID), per-step statuses, counts and output
summaries. Running tasks, queued tasks, human review, failures/interruption, paused
work and approved delivery are distinguished. A running segment task waiting for
indexing is shown as waiting at the segment step. Review can be available while Edie
works; the action banner explains the available human step without hiding background
work. Activity includes scoped retries/resume, failures and output ownership.

The dashboard polls every ten seconds. All job statuses refresh, not only the selected
job. Header/progress updates preserve playback and dirty forms. Newly prepared library
rows refresh automatically only when no media is playing and no relevant form/draft is
being edited; otherwise a refresh notice appears. Counts describe actual source and
segment coverage, not a guessed percentage of reasoning time. Parent Activity includes
its outputs' tasks; an output sees its own tasks and shared library work.

## Output identity and ownership

Outputs reuse the existing durable workflow/render machinery, represented internally
by a job record with `output_of` and `output_name`. `output_of` points to the root job.
They are omitted from the top-level `GET /jobs` list and listed under their parent.
The dashboard's workspace selector switches between the job library/proposals and a
named output without creating duplicate top-level jobs.

The library owner is resolved centrally for file intake, segments and source proxies.
Outputs share source versions, evidence, intake and segment decisions. These records
are not copied into diverging per-output libraries. Changing a shared selection
invalidates confirmation for every affected output; old script references cannot
silently use changed/rejected segments. Actual accepted timeline/master records remain
preserved. Context changes retain the existing explicit private-context workflow.

Each output has an independent script snapshot, instructions, workflow version,
feedback, approvals, revision, render tasks, export/delivery package and usage ledger.
Approving or revising one output does not approve or replace another. The output
inherits the parent brief, source scope, configured context reference and per-video
limits at creation. Custom output-specific formats/brief editing are not added here;
existing post-main-approval derivative functionality remains separate.

## API and review contract

- `GET /jobs/{root}/outputs`: named output IDs, briefs, titles, stages and approval
  summaries. The dashboard uses the existing `/jobs/{output}/...` workflow, feedback,
  preview and delivery APIs for each output.
- `POST /jobs/{root}/outputs`: `{request_id, name, script_candidate}`. The candidate
  is an exact proposed-script hash. Current library confirmation is required and all
  source/segment references and reject exclusions are revalidated.
- Creation atomically saves an independent script snapshot and empty approvals, in
  review-script state. It neither renders nor approves the script. Request IDs are
  idempotent; reusing an ID with different input is rejected.
- The user can select another proposal and create another output, then separately
  approve each script, review its rendered cut and approve delivery.

The parent is the dashboard's planning workspace. Named output workspaces expose cut
approval. Pause/cancel actions are scoped: parent library work and planning are separate
from already-created output workflows; cancelling an output does not cancel siblings.
The direction box and unsent instruction drafts follow the selected workspace. Shared
library drafts remain shared and block confirmation until saved/discarded.

## Source properties and presentation

Footage exposes selected original ffprobe properties: file size, encoded/display
width and height, portrait/landscape/square orientation, rotation, average frame rate,
video/audio codecs, audio-track count, pixel format and HDR indication. Display geometry
accounts for sample aspect ratio and rotation. Missing properties stay unknown; no VFR
claim is inferred from average frame rate. Full ffprobe metadata, environment data or
storage credentials are not exposed. Original metadata is reused; no reprobe is run per
poll. Source cards show orientation/size and the detail panel shows the complete summary.

The layout uses a consistent spacing scale, distinct job navigation and status banner,
numbered workflow cards, output cards, structured file-property rows and clear selection
states. Desktop has a separate direction panel; tablet stacks it; phone navigation and
workflow cards scroll locally rather than widening the page. Controls have visible focus
states and semantic labels, and animation respects reduced-motion preference.

## Verification and limits

Tests cover idempotent output creation, shared-library invalidation, separate approvals,
rotated media properties and progress derived from evidence rather than stale stages.
Two independent synthetic story outputs are built and rendered to distinct actual MP4
artifacts. Browser acceptance covers output creation/switching, approval isolation,
queued status, file properties, range editing and desktop/tablet/phone layouts.
Production job libraries remain subject to human footage/segment review; no live story
or render approval is created by deployment. Finishing-application roundtrip and final
editorial quality acceptance remain outstanding.

Activity reports durable queued tasks separately from requested agent work. A requested
edit remains Queued until a worker is observed running; requesting work alone is not
evidence of an active render. Root job counts include requests on its outputs.

### Segmentation recovery diagnostics

Segment workers report allowlisted failure codes for invalid/incomplete partitions,
cuts inside speech, invalid schema, context limits, changed sources, subscription
unavailability and timeouts. Unknown failures retain `segment_index_failed`. Only
these codes pass from child stdout to task results; raw exception text, stderr,
transcripts and provider responses are not exposed. Older generic failures cannot
be diagnosed retrospectively from their stored code alone.

Recovery reuses validated window caches and completed per-source segments, preserving
human edits. A diagnostic planning pass may populate the same validated cache without
publishing new segment records; subsequent leased execution validates and saves them.
No paid fallback or automatic approval occurs. Unit checks cover the code allowlist
and suppression of private exception text.

### Story-planning context and proposal limits

The agent snapshot remains capped at 190 KiB of canonical JSON, not 190k tokens and
not the provider model's context window. It retains all scoped source discovery rows,
with up to six ranked segment references per source. Segment discovery contains IDs,
bounds, labels, selection and scores; title/reason excerpts are capped at 160/240
characters. Full evidence remains intact and is available via `read_sources` before
scripting. Private editorial context, brief and workflow gates are preserved. Older
observations may be omitted with an explicit count. If required context still exceeds
the cap, the agent fails with a specific planning-context message before any model call.

`propose_stories` accepts 2–10 distinct source-linked proposals, validating all source
ranges before saving them. Ten is a ceiling, not a quota; unsupported stories must not
be invented. Each option remains subject to independent output creation and approval.
Model selection is deployment configuration, not hardcoded in reusable Edie code.

When tool evidence makes the snapshot too large, older observations are removed first,
but the latest observation is retained. The discovery list then falls back to source
IDs, paths, durations, intake decisions and segment counts, with an explicit compaction
notice. It never silently discards the source evidence the agent just requested. If
even the minimal catalogue plus latest evidence exceeds the cap, planning stops with
the context-limit diagnostic. A large-library regression includes a 140 KB tool result.
