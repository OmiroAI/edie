# Visual analysis and review pipeline

Status: target design; a first [local frame extractor](footage-index.md) is
implemented, but adaptive analysis and VLM review are not. Defaults are unbenchmarked. Model input compatibility must
be verified against the configured endpoint before enabling this pipeline.

## Purpose and boundaries

Create reusable, source-linked visual metadata without sending full-quality
footage to the VLM. Keep originals untouched for final rendering. Transcription
is a separate audio pipeline; combine its timestamped output with visual
observations downstream. Run preprocessing locally on broker-authorised copies.
Only explicitly permitted endpoints may receive media, including derived frames
and proxies. Small derivatives remain private project material.

Compressed file size alone is not an inference budget: frame count, resolution
and the model's visual-token accounting determine the input workload. Cap these
as well as request size, context usage, concurrency and per-job spending.

## Processing stages

1. **Inspect and prepare.** Probe streams, duration, orientation and source timing;
   verify broker source identity/version and compute a content hash. Detect shot
   boundaries, create a lightweight preview, and extract audio for transcription.
   Record source presentation timestamps, including variable-frame-rate and
   rotated media. Do not infer source time from proxy frame number alone.
2. **Coarse visual pass.** Split preferably at shot boundaries. Initial benchmark
   candidates are 30–60-second chunks, roughly one frame per second, and a
   448–640-pixel long edge, preserving aspect ratio. Include a small configurable
   overlap and bound the maximum frame count per request. These are tuning
   candidates, not established model limits or guaranteed adequate settings.
3. **Targeted inspection.** Increase sampling around demonstrations, reactions,
   fast movement and uncertain events. Request higher-resolution frames or crops
   for product labels, screens and small details. Quiet talking-head footage can
   use fewer visual samples. Uncertainty and editorial relevance drive escalation
   within the budget; exhausted budgets leave explicit gaps, not invented facts.
4. **Merge into the footage index.** Return timestamped descriptions, useful
   moments, segment categories, transition cues and uncertainty. Deduplicate
   overlap observations using source time, retaining their evidence references.
   Merge with transcripts without treating visual guesses as spoken words.
   Annotated filenames and existing draft documents are hints, not verified facts.
5. **Review the rendered revision.** Analyse a proxy made from the actual export,
   with denser inspection around edits, transitions, graphics and subtitles.
   Bind findings to that export hash and job/revision, mapping output time back
   to timeline/source ranges where possible. Changed revisions need fresh review
   for affected regions and their surrounding transitions.

## Inputs, outputs and caching

Each analysis request records source ID/version/hash, source time interval,
sample timestamps, preprocessing settings/version, model identity and prompt
version. Prefer native video-with-timestamps if the deployed endpoint supports
it correctly; otherwise use ordered timestamped images and document the reduced
temporal capabilities. Verify frame limits, resizing and timestamp interpretation
with a small capability test; do not assume image support implies video support.

Store structured observations with source start/end times, evidence frame IDs,
description, categories, uncertainty and any follow-up inspection request. Keep
reusable observations separate from story-specific selections and edit decisions.
The external broker receives the index and any proposed organisation changes;
Edie holds no remote-storage credentials.

Cache by source content hash, source interval, preprocessing settings/version,
model identity, prompt version and any context that affects the result. Scope
caches to the private project by default. Preserve stable broker IDs across
renames; changed content invalidates affected analysis. Record completed chunks
atomically, retain attempt/usage records, and resume only missing or invalidated
work. A partial index must expose its coverage and failures.

## Validation and human review

VLM review supplements deterministic checks on the full-quality export: decoding,
expected format/duration, missing media, audio/video timing, and subtitle bounds
and synchronisation. Sparse sampling cannot certify every frame or detect every
short visual defect. Retain human approval and the actual finishing-application
round-trip acceptance gate.

Before bulk indexing, benchmark representative authorised clips: talking heads,
small text/products, rapid reactions, motion and shot changes. Compare coarse
results with denser inspection and human observations. Measure missed moments,
timestamp accuracy, uncertainty, latency, peak memory and actual token/cost use.
Verify overlapping chunks, source/proxy time mapping, cache invalidation and
interruption recovery. Select defaults from those results, not model claims.

## Reference

[Qwen3-VL input utilities and examples](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md)
describe frame sampling and video preprocessing. This is a design reference,
not proof of support or limits for the deployed model and serving stack.
