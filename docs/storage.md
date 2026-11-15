# Deployment storage policy

Status: proposed. Current code retains all files; no quotas or garbage collector
are implemented. Never imply an existing cache is automatically managed.

Each deployment has independent private state/context and explicit read-only media
and asset mounts. The external broker owns local source-copy lifecycle and remote
originals. Edie can report references/release eligibility, but cannot delete sources.
Keep source copies while any unfinished job or retained editable package needs them.

## Allocation and reservations

Configure a working-storage quota, minimum filesystem free-space reserve, maximum
concurrent media tasks and artifact-retention policy. Admission checks both the
quota and actual filesystem headroom. Reserve estimated peak scratch bytes before
starting extraction/rendering; account for temporary outputs and final copies.
Estimates use duration, output settings and measured history, with a safety margin.
A reservation is not a filesystem guarantee: monitor free space during work,
handle ENOSPC explicitly, retain valid checkpoints and pause new admissions when
the reserve is threatened. Containers sharing a filesystem need a shared allocator
or independent filesystem quotas so they cannot each reserve the same capacity.

## Retention and cleanup

| Data | Retention rule |
| --- | --- |
| Broker media/assets | Read-only; broker decides removal after dependency checks |
| Context, feedback, source catalogue and decision records | Durable; explicit archive/export policy |
| Accepted edits, human-returned masters and delivery packages | Pinned; explicit operator archive/removal |
| Referenced editable media/graphics/subtitles | Pinned with the package that requires them |
| Frames, proxies and reproducible intermediates | Evict only if unreferenced by active work and not pinned |
| Failed attempts and incomplete files | Retain diagnostic metadata; cleanup after task reconciliation and grace period |

Start with a dry-run cleanup plan listing category, bytes, references, eligibility
and reason. Recheck references, leases and expected file hashes under a cleanup
lock before deletion; never follow symlinks outside owned cache roots. Interrupted
cleanup is resumable and cannot mark an existing artifact deleted prematurely.
Future automatic eviction is limited to eligible reproducible caches, oldest-used
first. If protected data fills the quota, require archiving or increased capacity.
There is no automatic deletion of accepted outputs to make room.

Backups require a consistent SQLite snapshot and referenced artifacts; copy while
writers are stopped until an online backup protocol is implemented. Archives must
be verified before an operator elects to remove local copies. Disk use should be
visible by originals (external), cache, scratch, retained outputs and reservations,
with cleanup candidates and blocked admissions exposed through the future API/UI.

## Context-window space

Context tokens are budgeted separately from disk bytes. Keep a compact durable job
summary with source references; retrieve bounded transcript ranges, frame evidence
and feedback as needed. Never truncate away human constraints or accepted edits.
A full context window causes summarisation/retrieval or a visible pause, not loss
of the underlying private records.
