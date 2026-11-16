# Files, segments and scripts

Implemented in the editorial runtime. Files are intake units; segments are reusable
story beats; scripts select and order segment trims. Original files are never split
or deleted. Human finishing-application acceptance is still outstanding.

## File intake

The dashboard exposes Keep / Exclude / Unreviewed. Keep makes a source available;
it does not require using it. Exclude removes all its segments from planning, without
deleting anything. Unreviewed blocks selection confirmation in segment workflows.
Intake requires an explicit decision. Model suggestions never count as human
review. Obsolete file-role editing/classification and runtime label translations
have been removed. Operators migrate development records explicitly.

## Editorial segment proposals

A text-only Codex reasoning pass receives the job brief, deployment private context,
transcript, visual observations, candidate pauses/scenes and neighbouring evidence.
It chooses coherent thoughts, exchanges, reactions, demonstrations or visual actions
and explains each boundary. A whole video can be one segment. Unboxing favours
reveal/action plus reaction; brain dumps favour complete thoughts/exchanges; event
coverage favours discoveries; B-roll favours continuous usable visual actions.
The brief/context can specify granularity. There is no fixed segment length.

For bounded requests, long sources are divided at candidate safe boundaries after
approximately three minutes, with ten seconds of neighbouring evidence. Boundaries
between requests remain fixed: cross-window semantic merging is a human operation.
An uninterrupted range may be longer. At most 100 transcript cues and 40 observations
are sampled evenly throughout a request, with omission counts disclosed. The planner
rejects malformed partitions and cuts inside valid ASR utterances. These checks do
not guarantee semantic completeness or frame/word-accurate alignment.

Roles overlap: A-roll, B-roll, Hook, Demonstration, Reaction, Establishing, Blooper,
Star and Needs review. **Blooper is not rejection**: it denotes an evidenced slip,
failed take, interruption, mishap or funny unexpected reaction. Preserve its setup
and payoff. Do not manufacture humour or infer unseen failures.

Each segment has an intrinsic usefulness `score`, separate `story_fit` (fit to the
current job brief), a reason and a boundary explanation. Scores are 0–100 editorial
judgements, not probabilities. Story fit is not a permanent score for every future
angle. The story agent must explain why chosen beats fit its proposed angle.
Human selection is separate: Available / Selected / Rejected. Selected prioritises
a moment without forcing it into every script. Low scores and blooper labels never
automatically reject footage. Selection is required explicitly; reject is not a role.

## Script references and human authority

New clips and overlays reference `source_id`, `segment_id`, source-relative `in` /
`out`, and purpose. Trims must fit inside the referenced segment; a script need not
use the whole segment. References persist segment bounds in the saved script.
Rejected overlaps, missing/deleted segment IDs and changed bounds prevent approval
or construction of an edit. Use multiple beats for multiple segments. Surrounding
two-second context handles support preview; they are not implicitly included in cuts.
File-only scripts are unsupported; development drafts were cleared for regeneration.
Existing accepted timelines/masters are retained under the existing authority rules.

Source partitions are keyed by job/source ID/version/hash and have a revision.
Split gives the two children new IDs. Merge gives a new ID and resets labels and
scores. Range editing updates both shared edges atomically and flags affected segments
for review. Neighbour selections are preserved, including rejects. Shortening the
first/last segment creates reviewable leading/trailing material. Neighbours cannot
be consumed by dragging; use merge for that. All operations retain source coverage.
Human edits protect the entire source partition from automatic regeneration.
Every save is recorded in `segment_events`; undo UI is not yet implemented.

Exact segment records and file decisions participate in footage confirmation.
All kept current sources need segments and all files need intake decisions. Changes
invalidate confirmation; preparation never approves footage, scripts or renders.
Workflow: review file intake → review segments → confirm selection → choose story
and review its trims → approve script → render. Refreshing model suggestions cannot
overwrite file intake or human segment edits.

## API and operations

- `POST /jobs/{job}/sources/{source}/disposition`: current source version/hash,
  `expected_revision` (classification revision), `disposition`, and `reason`.
- `POST /jobs/{job}/segment-tasks`, `{}`: idempotently queues profile-2 preparation
  for the current source collection. Existing human partitions are retained; old
  machine-only profile-1 partitions are upgraded. Waits for source indexing.
- `GET /jobs/{job}/footage`: includes file `disposition` and `segments` records.
- `POST /jobs/{job}/sources/{source}/segments`: current source version/hash,
  `expected_revision`, `segment_id`, and action: `label` (`labels`, `selection`,
  `reason`), `split` (`seconds`), `merge_next`, or `range` (`start`, `end`).
- `python -m edie.segments --state /state --media /media --socket /run/edie/codex.sock`.

Tasks use existing leases, cancellation, pause and explicit recovery. Workers have
private state, read-only media and a permitted text broker socket, no network or
storage credentials. Valid model responses are cached by evidence/context/schema;
completed source partitions checkpoint independently. Interrupted uncached calls
can have unknown usage; never assume retries are free. Usage is recorded locally.
There is no paid fallback. Model-route budgets and subscription accounting retain
the limitations documented in runtime workflow docs.

Checks cover valid partitions, mid-speech rejection, cache reuse, separate scores,
blooper availability, stale/source-version writes, human protection, segment script
references and rejected-range enforcement. Browser checks cover intake, filtering,
playback, Blooper/selection controls, save-next and split. Real editorial quality
still requires review of actual footage.

## Visual range editor

The segment review panel has two draggable handles, exact start/end fields, keyboard
slider controls, seek-start/end, draft-range playback, neighbour view and zoom-to-range.
Load filmstrip decodes ten frames from the existing local review proxy in the browser;
no model call, upload or new permanent media is involved. Frames are drawn to canvas
under the existing Content Security Policy. Draft boundaries remain local until Save
segment range. Unsaved drafts block selection confirmation; stale revisions cannot save.
Changing ranges resets affected roles/scores to Needs review and recomputes context
handles. Preview timing is proxy-based, not a promise of frame-exact finishing accuracy.

`POST .../segments` action `range` accepts both bounds in one revision-checked write.
The old one-sided `boundary` action and `/classification` endpoint are removed.
Index workers no longer trigger whole-file role classification; segment workers own
editorial roles. Running older worker containers may finish their current jobs before
being upgraded; indexing caches and live segmentation are not discarded.
