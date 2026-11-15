# Broker source catalogue and local preprocessing

Status: initial implementation. No model requests, transcription or remote
storage changes occur. This is the local foundation of the target pipeline.

Import a JSON array using `edie --state STATE ingest PROJECT MANIFEST --media MEDIA`.
Each entry requires `source_id`, `version`, `path` (relative to the authorised
mount) and `sha256`. The broker owns authoritative IDs/versions; Edie verifies
local hashes. A manifest is committed atomically. Reusing an ID/version with a
different hash fails. A rename updates its local path without losing identity.
New versions retain historical metadata; old media must remain available if
active revisions need it. Source versions are opaque, not lexically chronological.

Prepare frames with:

```
python -m edie.preprocess --state STATE --media MEDIA --project PROJECT --source-id ID --version VERSION
```

The library permits bounded chunk duration, overlap, sampling rate, image size
and frame count. Defaults are 30 seconds, 2 seconds overlap, 1 fps and 640-pixel
long edge. These defaults are unbenchmarked. Selected original decoded frames
retain source-relative presentation times; timestamps are measured from the first
decoded video frame, not wall clock or proxy frame number. Audio alignment still
needs a shared stream-origin mapping before transcript integration.

The private project cache key includes source hash and preprocessing settings/
version. Each completed chunk stores frame paths, timestamps, sizes and hashes.
Interrupted work leaves completed chunks reusable; missing/corrupt cached images
cause that chunk to rebuild. Unique attempt directories preserve previous files.
Concurrent calls can duplicate extraction but cannot share writable frame files.
No partial file is treated as a completed chunk manifest.

The current implementation decodes each source from its beginning for each chunk
for straightforward timestamp handling. This is inefficient for long footage;
seek-aware extraction and bounded stderr streaming are follow-up work. It does
not detect shots, create proxies, extract audio, perform adaptive inspection or
call a VLM. Current tests cover constant-frame-rate timestamps, chunk reuse,
missing-image recovery, rename identity, version conflicts and frame-budget
rejection. An authorised real clip also produced six timestamped frames with verified cache
reuse. This is a preprocessing check, not a visual-understanding benchmark.
Variable-frame-rate/rotation and model capability tests remain required.
