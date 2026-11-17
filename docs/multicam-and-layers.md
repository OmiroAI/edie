# Multicam sessions and audio-led editing

Status: implemented. Synthetic offset/drift checks, a real FFmpeg layered render,
and browser review tests cover the core path. Real authorised footage has produced
alignment candidates and sync previews. Uncertain-sync review and an actual
finishing-application roundtrip remain acceptance gates.

## Editorial model

Camera identity describes where a recording came from; it does not replace Keep /
Exclude or segment roles such as hook, A-roll, B-roll or blooper. A presenter camera
can contain detail shots, and a product camera can contain useful dialogue.

A job's shared library owns private capture configuration and sync sessions. Its
independent story outputs reuse these records. `audio_led` is the default: dialogue
clips establish the sequence, while independently timed B-roll covers selected
parts without replacing the dialogue. `multicam` adds reviewed relationships
between recordings of the same event. Camera identities and session membership are
operator-configurable; Edie does not infer simultaneous coverage from a B-roll label.

A proposed session records an anchor, a preferred audio source and versioned source
members. The preferred source guides planning; dialogue may use other presenter
recordings in the session. It is not an automatic audio-quality verdict.

## Local alignment pipeline

Prepare source review copies first. A network-disabled sync worker reads those
copies, verifies their hashes and original source references, and extracts mono
8 kHz audio. RMS envelopes at 100 Hz provide a compact signal for normalized
cross-correlation. Three windows spanning each member recording are matched
against the anchor. Windows are at most 20 seconds long. A strong candidate needs
at least two windows with correlation >= 0.65, separation from alternative peaks
>= 0.08, and offsets agreeing within 0.08 seconds. These thresholds describe signal
evidence, not a probability or human approval. Flat, missing, ambiguous or drifting
audio remains uncertain.

All times are seconds. The convention is:

```
group time = source time + source offset
alternate source time = dialogue source time + dialogue offset - alternate offset
```

Offsets may be negative; the anchor remains zero. A session supports 2–32 selected
sources and review recordings up to two hours. Included sources must share at least
one second with the anchor when durations are known. Automatic matching needs at
least ten seconds of usable audio. Constant offsets are supported; clock-drift
retiming, timecode-based matching and arbitrary nested multicam timelines are not.
Detected drift above 0.08 seconds blocks constant-offset confirmation.

The worker accepts strong, consistent, source-current matches automatically and marks
uncertain matches for review. When every included member qualifies, it confirms the
session with `approval_origin: automatic`, not a fabricated human approval. In
Footage → Cameras & sync, the reviewer can
inspect or adjust offsets, omit a member from the session, choose preferred audio,
and explicitly confirm remaining uncertainty. Omitting a member here does not exclude its file or
segments. Only uncertain members are expanded in the review queue. Automatically accepted
matches remain accessible under “Inspect accepted matches and reference camera”.
Uncertain members need manual alignment or omission before confirmation.
A rejected session can be revised and confirmed. A confirmed session is immutable;
reject it and propose a replacement to realign it.

The optional Check sync button creates an eight-second (or shorter) side-by-side preview at the middle
of shared coverage: anchor picture on the left, member on the right; anchor audio
in the left channel, member audio in the right. Activity lists the completed
previews. This sample is an aid, not proof of frame-accurate sync across a recording.
Sessions with unresolved uncertain members block footage confirmation and story planning.

## Scripts, layers and rendering

Stories and Cut show an Audio/Picture plan plus compact dialogue, primary-picture,
coverage and graphics lanes. Existing scripts are projected into this view without
rewriting their content or approval hashes. They do not gain invented coverage.

The canonical script still stores `clips`, `overlays` and `titles`. Primary clips
carry their original audio. Coverage is muted and may be either:

- Independent B-roll: explicit source/segment identity, in/out, output `at` and purpose.
- Alternate camera: `sync_group_id`, `sync_capture_revision`, `source_id`,
  `segment_id`, output `at`, `duration` and `purpose`. The resolver derives source
  trims from the confirmed offsets. Each overlay must fit within one dialogue beat
  and an eligible source segment, and overlapping coverage is rejected.

Resolved alternate-camera coverage carries a group hash. Output creation, script
approval and timeline construction reject a changed/rejected sync relationship.
Normal source version, range and exclusion checks still apply. Existing accepted
renders are not rewritten by capture changes.

The OTIO timeline uses primary picture, dialogue and muted picture coverage tracks.
Subtitles follow the dialogue edits, not the overlaid camera's transcript. FFmpeg
renders actual picture switches with continuous primary audio. This is a constrained
audio-led rough-cut model, not a general multitrack audio mixer or NLE. Initial
handoff remains FCP 7 XML, SRT, linked media/assets and MP4; actual target-editor
import and return need separate verification.

## API and persistence

All endpoints use the existing bearer authentication and root-library scope.
Mutation bodies carry `expected_revision`; stale writes fail rather than overwrite.

| Route | Fields / result |
| --- | --- |
| GET `/jobs/ID/capture` | Revision, mode, source camera map, session groups |
| POST `/jobs/ID/capture/configure` | `mode`, `sources` map covering current sources; each entry has `camera_id` and `role_hint` (`dialogue`, `detail`, `unknown`) |
| POST `/jobs/ID/capture/discover` | `name`, selected `source_ids`, `anchor_source_id`, `primary_audio_source_id`; returns capture and queued task ID |
| POST `/jobs/ID/capture/preview` | `group_id`, member `source_id`, optional manual `offset`; returns durable task |
| POST `/jobs/ID/capture/confirm` | `group_id`, `included` source IDs, `offsets` map for those IDs, `primary_audio_source_id` |
| POST `/jobs/ID/capture/reject` | `group_id` |
| POST `/jobs/ID/capture/accept-confident` | `group_id`, `expected_revision`; apply evidence-based triage to an existing proposal |
| GET `/tasks/ID/artifact` | Completed sync preview, authenticated MP4 |
| GET `/jobs/ID/workflow` | Existing workflow plus derived `layers` view |

`captures` stores the current revision; `capture_events` stores private revision
snapshots and actor labels. No footage decisions, segment edits or workflow approvals
are rewritten. Jobs without capture configuration read as audio-led revision zero;
without sync groups their existing footage-confirmation identity stays unchanged.
Migration therefore configures cameras/sessions separately and verifies those
existing editorial records remain identical.

Run `python -m edie.capture --state /state --worker` in the configured sandbox,
with FFmpeg and NumPy available, writable state and review copies. It processes
`sync_index` and `sync_preview` through the durable task/lease mechanism. No host
credentials, media upload, Docker socket or network access is needed. API and
coordinator deployments must use the matching code version.

Task controls use the ordinary pause/resume/cancel/recover endpoints. Sync results
are revision-fenced: configuration changes while analysis runs prevent stale writes.
A task interrupted after committing its capture result must be reconciled against
that saved revision; retrying its old payload cannot silently overwrite it. Preview
requests are keyed by their configuration and payload; failed previews can be
explicitly recovered. Completed preview files are immutable and SHA-256-verified through
task results. They use normal storage admission and deployment retention controls.

## Visual alignment review

Footage → Cameras & sync → **Open alignment editor** opens an in-place review
workspace. Camera naming and new-session configuration are under Advanced setup.
The editor has two original review-copy players, linked transport, a shared-range
scrubber, and selectable reference/member/both audio. Both audio is useful for
hearing doubled speech. It loads authenticated lightweight proxies into browser
blob URLs; it does not send media to a model. Long proxies can take time to load.
URLs are revoked and playback stopped when the dialog closes.

The paired waveform lanes show a ten-second window centred on the reference
playhead. Click either lane to seek. Waveforms are locally extracted normalized
RMS envelopes (20 samples/second), not sample-accurate audio or loudness comparisons.
Use Earlier/Later 0.1s or 0.01s to change the member picture while keeping the
reference time fixed. For a missing/incorrect proposal, choose **Find matching
moments independently**, seek each player's native controls to the same gesture
or sound, then **Match these two frames**. This sets offset to reference time minus
member time. Play together and inspect several points across the shared range.
The browser periodically corrects playback drift; paused seeking and rendered
sync-check previews are the more precise checks. Browser playback is not a
frame-locked finishing-editor preview.

**Use this alignment** copies the offset into the session draft. It does not
approve the session. Cancel/Close discards changes made inside that dialog. After
reviewing all included members, **Confirm reviewed synchronisation** persists the
whole session with its revision/source checks. A page refresh discards unconfirmed
session drafts. Confirmed sessions open read-only. No existing decisions are changed
by opening, playing, adjusting or cancelling a pair.

POST `/jobs/ID/capture/waveform` accepts `source_id` and returns a durable
`sync_waveform` task, deduplicated by current source version/hash. The offline sync
worker verifies the review copy and returns `kind`, `source_id`, `step` (0.05s)
and `peaks` in its task result. At most two hours of source audio are accepted.
A source without audio completes with an empty waveform and explanatory note;
picture-based manual alignment remains available. Extraction failure is visible in
Activity and uses normal explicit task recovery. This read-only derivative does
not mutate capture revisions or require a capture approval. Dashboard polling
waits while the editor is open so it cannot replace draft controls during review.

Automatic triage uses the existing multi-window correlation/margin thresholds,
requires offsets to agree within 80 ms, checks drift, source versions and overlap,
and records its own actor in the capture audit. It never approves footage selection
or scripts. Existing proposals can be migrated through `accept-confident` without
re-indexing or changing the source offsets. Confident members are hidden from the
required review list; uncertainty remains visible.
