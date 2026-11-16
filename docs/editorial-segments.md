# Editorial segments

Implemented: job-scoped, versioned source ranges with labels, usefulness scores and
human split/merge/boundary controls. Originals are never split into physical files.
These are default editorial units, not indivisible restrictions on final trims.

The initial boundary proposal uses valid transcript pauses, sentence endings and
visual scene-change candidates. It avoids cutting through a valid ASR utterance,
requires six seconds since the preceding proposed boundary and leaves at least
three seconds at the end. These are conservative heuristics, not semantic detection
or frame-accurate alignment. Long continuous speech/action may remain one segment;
the editor can split it. Silent footage uses scene evidence where available.

A configured text-only Codex route assesses each segment against the job brief and
private style context. It receives overlapping transcript/visual observations and
returns labels, a 0–100 usefulness score and a reason. Scores sort across the job;
they are not probabilities. File-level labels remain separate. A rejected file
excludes all its segments. A rejected segment prevents overlapping source trims
in new agent scripts and script approval. Existing accepted edits remain stored.

## Storage and review

`segments` stores a revisioned partition per job/source ID/version/hash, with stable
segment IDs and source-relative start/end seconds. `segment_events` retains every
saved version. Save requires the exact revision and current source version/hash.
Split creates two new IDs. Merge creates a new ID and resets labels to needs-review.
Moving a shared boundary updates both neighbours and flags their labels for review.
All ranges must be finite, nonoverlapping and cover the entire source. A reject is
an exclusion label, never a gap or media deletion. Human edits protect the entire
source partition from automatic replacement. No generated pass resets human labels.

The exact segment partition and labels participate in footage-confirmation hashing.
When a segment task exists, all current indexed sources must have segment records
before confirmation. Changed boundaries/labels invalidate the previous selection.
The user confirms in Footage after reviewing Segments; preparation never approves
footage, scripts or renders. Story selection must be reconfirmed after changes.

## API and workers

- `POST /jobs/{job}/segment-tasks`, body `{}`: idempotently queue preparation for
  the current source collection. The task waits for active source indexing. The
  worker uses the existing task lease, cancellation, pause and explicit recovery.
- `GET /jobs/{job}/footage`: each source includes `segments` with revision, human
  protection flag and items. Dashboard Segments sorts by usefulness, source order
  or duration and filters labels. Playback uses the existing source proxy.
- `POST /jobs/{job}/sources/{source}/segments`: body includes `source_version`,
  `source_sha256`, `expected_revision`, `segment_id` and `action`. Actions:
  `label` (`labels`, `reason`), `split` (`seconds`), `merge_next`, `boundary`
  (`seconds`, moves the selected segment's end and next segment's start).
- Worker: `python -m edie.segments --state /state --media /media --socket /run/edie/codex.sock`.
  Runtime needs only existing private state/media mounts and permitted text broker.
  No storage credentials or network access are required.

Completed sources checkpoint independently. Restart skips existing partitions;
failed in-progress source assessments may need replay and associated usage must be
reported. Source replacement creates a new partition; old review records remain.
Suggestion regeneration over an existing human partition and segment-level undo UI
are not implemented. Audit history is retained for operator recovery.

Automated checks cover boundary generation, invalid ranges, stale writes, source
version isolation, human protection and rejected-range exclusion. Browser checks
exercise segment playback, labels, save/next and splitting with synthetic footage.
Real-footage editorial quality still requires human review.
