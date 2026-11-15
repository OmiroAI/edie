# Private configuration and memory

Implemented: operator-managed context versions, editable Markdown, explicit
activation and rollback, and a context reference pinned when each job is created.
Model prompt assembly and automatic learning are not implemented yet.

Set `EDIE_CONFIG_DIR` to an absolute private directory outside the checkout:

```text
configuration/
  context/
    SOUL.md
    MEMORY.md
    active.json
    versions/<sha256>.json
```

SOUL.md describes the deployment's editorial direction, Edie's personality,
collaboration expectations and human authority. MEMORY.md holds concise accepted
lessons and decision history, including source job/revision, approval, scope and
superseded entries. Neither is a dumping ground for raw conversations, credentials
or render output. Detailed task history belongs in private state records; a full
append-only operational event journal remains planned. Rejected drafts must not
become learned preferences. Story-specific requests stay with their jobs.

The Markdown files are editable working copies. Runtime jobs use immutable JSON
snapshots containing the structured strategy and captured `soul`/`memory` strings.
Working-copy changes have no effect until an operator snapshots and activates
them. The snapshot hash covers all context, including the Markdown. Editing a
version in place fails integrity validation. Missing configured context fails job
creation; a bare development Store without configuration still allows tests and
context-free jobs. Old jobs never automatically adopt newer context.

Bootstrap from a private JSON strategy with `schema_version: 1`, nonempty
`strategy_id`, `version` and `rules`. Each rule needs unique `id`, `kind` and `rule`:

```sh
export EDIE_CONFIG_DIR=/absolute/private/configuration
python -m edie.context install /absolute/private/strategy.json
python -m edie.context activate PRINTED_HASH --expected none
# Create/edit context/SOUL.md and context/MEMORY.md privately.
python -m edie.context snapshot --version editorial-2
python -m edie.context activate NEW_HASH --expected PREVIOUS_HASH
python -m edie.context status
```

Activation compares the current hash under a lock, preventing stale operators
from overwriting another activation. To roll back, activate a retained older hash
with the current hash as `--expected`. New jobs adopt the rollback; existing jobs
remain pinned. Back up the entire configuration and state directories together,
with writers stopped, and retain versions referenced by jobs.

New directories are private (0700); generated files are 0600. Set Markdown file
permissions to 0600 too. Configure `EDIE_UID`/`EDIE_GID` to the owning account so
containers can read context and write state. Compose mounts only `context/`
read-only into CLI/API; the render-only worker does not receive it. Secrets may
live separately in runtime configuration but are never captured in context.
No API mutation, automatic context export or model upload is added by this change.
