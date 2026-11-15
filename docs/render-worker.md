# System design

Status: development implementation; not production-ready.

The management API and render workers share a private SQLite database in WAL
mode. Records hold jobs, immutable revisions, feedback and approvals.
The task table holds idempotency keys, inputs, leases, state and output metadata.
An external broker supplies read-only local footage; no storage credentials enter
Edie. Model orchestration and the footage index are future components.

## Render execution and recovery

A worker atomically claims a queued task using `BEGIN IMMEDIATE`, assigning a
unique owner and a 60-second lease. It launches a separate render process group
and renews the lease while monitoring that process. Only the current owner with
an unexpired running lease can publish completion. The worker validates the job
and revision binding again before execution.

Every attempt uses a new output directory beneath the immutable revision ID.
FFmpeg reads hash-verified local sources, renders normalised clips, concatenates
and validates duration and full decoding before publishing a preview file. The
completed task stores a state-relative artifact path, size, hash and revision.
Completion means a validated reference preview, not human approval or delivery.

Running pause/cancel requests become `pause_requested`/`cancel_requested`. The
worker terminates the process group, waits for exit, then acknowledges paused
or cancelled. Resume restarts rendering in a new attempt; this is not frame-level
checkpointing. Completed previews and partial attempts are retained.

A worker encountering an expired lease marks the task interrupted. Recovery is
explicit; there is no automatic replay. New attempts cannot overwrite old
attempts, and an expired owner cannot publish completion. A hard-killed worker
may leave a child running until its subprocess timeout/container shutdown;
operators should stop that isolated worker container before recovery. A crash
between artifact creation and DB completion can leave an unreferenced artifact;
recovery currently rerenders rather than adopting it. No automatic cleanup.

## Limits

One operator bearer token grants access to all jobs in this deployment. There is no
multi-tenant access control. API validation and renderer support remain limited.
Rendering currently requires audio and produces 720p/30fps previews. Concurrent
requests for the same revision may render separate attempts; artifacts are safe
from overwrite but redundant computation is still possible. Per-job budget
accounting, model execution, accepted-master precedence and the full editorial
approval state machine remain to be implemented.
