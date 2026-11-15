# Timeline representation: OpenTimelineIO

Implementation update: [runtime workflow](runtime-workflow.md) records the current
implemented subset, commands, validation and remaining limits. The detailed target
contracts below extend beyond that subset.

Decision: use OpenTimelineIO (OTIO) as Edie's canonical editorial timeline format.
Status: accepted design; integration is not implemented. Current revisions still
store flat clip lists, and the renderer does not consume OTIO yet.

## Why OTIO

[OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) is an
open editorial data model with Python bindings and format adapters. Use its clips,
tracks, gaps, media references and time primitives instead of inventing a complete
editing interchange format. This is a choice for Edie, not a claim that all video
agents use a common standard. OTIO does not supply Edie's renderer, approval system
or agent loop.

## Revision package

Each immutable revision will contain a `.otio` timeline and a versioned manifest
linking the job, parent revision, source versions, asset hashes and subtitle data.
The revision hash covers the complete package, not just the timeline. Stable clip
IDs and namespaced `edie` metadata connect edits to source IDs and evidence; retain
an external mapping because third-party interchange may discard custom metadata.
Paths are resolved through the authorised broker catalogue rather than treated as
permission to open arbitrary URLs or host files.

Keep feedback, approvals, strategy, transcript originals, model decisions and usage
in Edie's durable records. Store editable subtitle cues with stable IDs, language,
source provenance and revision-relative times alongside the timeline; derive SRT
from those cues after every timing change. SRT is a delivery format, not sufficient
storage for subtitle provenance or styling.

## Initial subset and feature policy

| Feature | Initial target |
| --- | --- |
| Ordered video/audio clips and explicit gaps | Supported first |
| Multiple tracks | Represent in OTIO; enable only after renderer/export tests |
| Source trims and timeline placement | Validate bounds and explicit timebases |
| Markers | Preserve where adapter permits; keep Edie records separately |
| Subtitles | Sidecar cue model; per-language SRT export |
| Graphics/assets | Versioned dependencies; no promise of editable native titles |
| Nested timelines | Defer execution until tested end to end |
| Transitions, effects, speed changes | Explicit unsupported-feature reporting until implemented |

The [FCP7 adapter](https://github.com/OpenTimelineIO/otio-fcp-adapter) lists tracks,
audio, gaps, markers and nesting as supported, but transitions, A/V effects and
speed effects as unsupported. Adapter capability alone does not establish renderer
support or successful import in a particular Premiere version. Pin OTIO and the
separately distributed adapter versions during implementation and test their subset.

Never silently drop a feature. Reject a required unsupported operation or offer an
explicitly approved rendered replacement with its editability loss documented.
Preserve the original timeline and assets even if an approved handoff uses baked
media. Expanding this subset remains necessary for the complete product requirements.

## Time and media rules

Use OTIO time values with explicit rates; retain exact source and sequence-rate
metadata, including fractional rates such as 30000/1001. Do not repeatedly round
through floating-point seconds. Define half-open ranges and an explicit conversion/
rounding policy at the renderer and XML boundary; reject nonrepresentable edits
where an automatic rounding change would alter approved timing.

Keep source presentation timestamps and audio offsets distinct from timeline time.
Variable-frame-rate sources need an explicit mapping or a normalised proxy with a
source map; a proxy frame number is not an original source frame number. Preserve
orientation, channel layout and media duration metadata for validation. Relinking
must verify broker source identity/version/hash, not only matching filenames.

## Agent tools and rendering

Expose validated operations such as insert, trim, move, replace, add-gap and adjust
subtitle timing. Each operation names stable objects and the expected base revision.
Apply a batch to a copy, validate the whole timeline, then commit one new revision
with a human-readable diff. A stale edit cannot overwrite a human's newer revision.
The agent does not need to rewrite an entire OTIO JSON document for every small cut.

Compile the supported OTIO subset into a deterministic render plan. The preview
renderer and handoff exporter consume the same committed revision package. Publish
artifact hashes and compatibility reports against that revision. Model judgement
cannot substitute for structural, timing or dependency validation.

## Handoff and human return

Use the selected [finishing-editor profile](editor-adapters.md). The first planned
profile is FCP7 XML plus SRT, linked media/assets and MP4 preview, as specified in
[handoff and feedback](handoff-feedback.md). Other formats/editors remain open;
OTIO remains Edie's canonical representation. Validate a basic
cut first, then expand the round-trip matrix feature by feature.

Import returned XML to a new human-authored OTIO revision. Reconcile clip IDs and
source/time references; surface ambiguous matches and unsupported changes instead
of guessing. Retain the received XML and manifest as immutable evidence. A returned
accepted master remains authoritative when no editable timeline is supplied.

## Implementation and validation sequence

1. Pin libraries; implement clip-list-to-OTIO conversion as a new revision while
   retaining legacy records and previews. No destructive automatic migration.
2. Implement basic timeline validation and render-plan compilation, comparing
   duration and cuts with deterministic synthetic fixtures.
3. Export/import FCP7 XML fixtures and verify media links, track placement, gaps,
   trims and rate conversion; detect adapter information loss.
4. Exercise the actual finishing application/version: import, change cuts, export,
   reimport and verify frame-level timing, audio and subtitles with real footage.
5. Add agent edit tools and stale-revision/conflict tests; then extend the supported
   effects/graphics subset only with matching renderer and interchange checks.

The initial library tests can run without Premiere. They do not establish finishing-
application compatibility; that acceptance step remains outstanding.
