# Transcript-guided visual indexing

The original development index inspected only eight 384px stills per source. That
was an implementation budget, not a measured model limit; it is inadequate for
long B-roll and brief actions. Existing coarse indexes remain usable while their
replacement is prepared. Never label them as dense or continuous inspection.

The adaptive pass (analysis version 4) uses:

- Baseline: approximately one decoded frame per second across the whole source,
  up to 512px on the long edge, with HDR-to-SDR conversion where necessary.
- Local scene-change detection at reduced spatial resolution, retaining decoded
  timestamps. Motion and flashes can also trigger it: these are candidate transitions.
- Transcript-guided six-second windows at two fps around action/reaction phrases
  and utterance boundaries with gaps, plus windows around scene candidates. Up to
  three nonoverlapping focused windows per minute; omitted-candidate counts are
  reported. The initial phrase matcher is an English heuristic, not semantic proof;
  baseline coverage is independent of transcript content/language.
- At most 32 frames per model request, further bounded by the configured route's
  max_frames. Each batch includes overlapping timestamped transcript excerpts.
  The prompt distinguishes words in the transcript from visually verified events.
- Agent `inspect_range` supports 1–4 fps over a selected range of up to 60 seconds,
  split into the same bounded local requests. Use short, dense ranges for uncertain
  moments; do not send full-quality originals or cloud media.

Density is a deployment/profile budget, not a claim to saturate the model's maximum.
Verify the running endpoint's context limit and practical frame/resolution request
capacity. Qwen's reference video processing also separates frame rate and pixel
budgets; model-family examples are not proof of a particular custom deployment's
limits ([Qwen documentation](https://github.com/QwenLM/Qwen3-VL)). The configured
endpoint's advertised limits and local request measurements take precedence.

The new pass retains original transcripts, invalid-ASR timing warnings and source
identity. `analyse` reuses prior speech/coarse results; `edie.adaptive --job ...`
can explicitly upgrade an existing job without retranscription. Frames, scenes and
individual VLM responses are cached. A partial run resumes completed model batches;
the published index changes atomically only after the full source pass succeeds.
Source hashes are checked before and after processing. Independent per-source locks
prevent duplicate workers. Storage admission accounts for baseline JPEGs; long sources
are bounded to ten hours. No deletion or paid fallback occurs.

The index reports actual sample count, largest temporal gap, batch count, focus
window count, omitted focus candidates and transcript references per observation.
The dashboard shows these coverage facts, progress and candidate cut timestamps.
Speech-pause candidates are ASR estimates. Scene candidates are visual-change
estimates. Neither constitutes frame-accurate editorial approval or forced alignment.
Final cuts still require source playback/audio checks and render/human validation.

Classification summaries sample at most 24 visual observations across a long source;
the complete visual index remains available for detailed inspection. Human label
overrides survive refreshed suggestions. A materially changed reviewed classification
requires a new footage confirmation; reindexing never manufactures it.

For an existing job, POST `/visual-index-tasks` with the job and current source
references plus an idempotency key. This route explicitly reuses existing transcripts
and fails on source-version mismatch; it never silently retranscribes. The offline
index worker resumes visual batches and refreshes suggested classifications after
the entire job batch completes. Human overrides remain authoritative.
